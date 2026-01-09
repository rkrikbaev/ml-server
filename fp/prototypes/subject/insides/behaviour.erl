
%%-----------------------------------------------------------------
%% This script is executed at the server side. The programming language
%% is Erlang.
%% The module MUST export next 3 methods:
%%  * on_create/1 - this method is called when a new instance of the prototype is created.
%%  * on_edit/1 - this method is called when own fields of an instance of the prototype are edited
%%  * on_delete/1 - this method is called when an instance of the prototype is deleted 
%% All this methods accept an Object of the instance and can edit or perform any other allowed code.
%% If any of the methods throw or crash the whole transaction will rollback.
%% If there are any warnings or not critical errors it is recommended to log them with available macros, examples:
%%  ?LOGWARNING( "my warning text: ~p", [Warning] )
%%  ?LOGERROR( "my error text: ~p", [Error] )
%% If the methods performs well it should return atom 'ok'.
%% For more info please refer to the documentation
%%-----------------------------------------------------------------
-module(fp_prototype_subject).

-include("fp.hrl").

-export([
    on_create/1,
    on_delete/1,
    on_edit/1
  ]).
  
-export([
    sync_archives/3
]).

-define(TRANSACTION_SIZE, 1000).

on_create(_Object)->
  ok.
on_edit(_Object)->
  ok.
on_delete(_Object)->
  ok.
  
  

sync_archives(FolderPath, Replica, Seconds)->
    Query = {'ANDNOT',
        {'AND',[
            {<<".pattern">>,'=',?OID(<<"/root/FP/prototypes/subject/fields">>)},
            {<<".fp_path">>,'LIKE', <<"^", FolderPath/binary>>},
            {<<"is_prototype">>, '=', false}
        ]},
        {<<"disabled">>,'=',true}
    },
    
    Items = fp_db:get('*',[<<".oid">>], Query),

    Archives = 
        lists:foldl(fun find_archives/2, #{}, Items),

    TS0 = ?TS,
    TS1 = TS0 + (Seconds * 1000),

    ArcData0 = read_archives(maps:keys(Archives), TS0, TS1),
    
    #{
        <<".folder">> := ContextOID,
        <<"guid">> := GUID,
        <<"urls">> := URLs,
        <<"timeout">> := Timeout
    } = fp_db:read_fields(fp_db:open(Replica), [
        <<".folder">>, 
        <<"guid">>, 
        <<"urls">>,
        <<"timeout">>
    ]),
    {ok, Context} = fp_db:read_field(?OBJECT(ContextOID), <<".fp_path">>),

    ArcData = 
        maps:fold(
            fun(A, V, Acc)-> 
                Acc#{ binary:replace(A, <<Context/binary,"/">>, <<"">>) => V}
            end, 
            #{}, 
            ArcData0
        ),

    Packet = #{
        type => fp_replica_ts_recv,
        version => {1, 0, 0},
        data => ArcData,
        guid => GUID
    },

    case fp_replica_transport_send:send(URLs, Packet, Timeout) of
        {ok, _} ->
            ok;
        {error, Reason} -> 
            throw( Reason )
    end.

find_archives(OID, Acc)->
    case fp_db:find_in_folder(OID, <<"archives">>) of
        {ok, ArchivesFolderOID} ->
            Query = {'AND',[
                {<<".pattern">>,'=',?OID(<<"/root/.patterns/ARCHIVE">>)},
                {<<".folder">>,'=', ArchivesFolderOID}
            ]},
    
            {_, Items} = fp_db:get('*',[<<".fp_path">>], Query),
            lists:foldl(
                fun([A], InAcc)-> 
                    InAcc#{ A => true }
                end, 
                Acc, 
                Items
            );
        _->
            Acc
    end.

read_archives(Archives, TS0, TS1)->
    Values = fp_archive:read(Archives, TS0, TS1),
    % Filter out empty values
    maps:filter(
        fun(_A, V)-> 
            is_list(V) andalso length(V) > 0 
        end, 
        Values
    ).