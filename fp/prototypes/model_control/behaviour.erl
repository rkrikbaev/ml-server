
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
-module(fp_prototype_model_control).

-include("fp.hrl").

-export([
    on_create/1,
    on_delete/1,
    on_edit/1,
    on_cycle/1
  ]).
  

on_create(_Object)->
    ok.

on_edit( Object )->
    ?LOGINFO("prototypes/model_control:on_edit"),
    fp_util:check_changes(Object, [
        {fun execute_model/1, [<<"run_task">>]},
        {fun load_data/1, [<<"output_data">>]}
        
    ]),
    ?LOGINFO("prototypes/model_control:on_edit ok"),
    ok.
    
on_delete( Object )->
    ok.
    
on_cycle( FolderPath )->
    Query = {'ANDNOT',
        {'AND',[
            {<<".pattern">>,'=',?OID(<<"/root/FP/prototypes/model_control/fields">>)},
            {<<".fp_path">>,'LIKE', <<"^", FolderPath/binary>>},
            {<<"is_prototype">>, '=', false}
        ]},
        {<<"disabled">>,'=',true}
    },
    
    fp_kegoc_util:on_cycle(Query,[
        fun execute_model/1
    ]).

execute_model(Object)->
    ?LOGINFO("before"),
    project_model_service:run_task(Object).

load_data(Object)->
    ?LOGINFO("load_data"),
    % Get output_data, model_name & path
    #{ 
        <<"output_data">> := BinaryString, 
        <<"model_name">> := ModelNameID, 
        <<".path">> := ObjectPath
    } = fp_db:read_fields(Object, [<<"output_data">>, <<"model_name">>, <<".path">>]),
    
    % Get model_output as Object + "/archives/out_value
    ModelOutput = ?OID(<<ObjectPath/binary, "/archives/out_value">>),
    
    Data = binary_to_term(BinaryString),
    case project_model_service:write_to_db(Data, ModelOutput) of
        {ok,[DataAsBinString,From,To]}->
            ?LOGINFO("Write to DB success");
        {error,_}->
            ?LOGERROR("Write to DB failed")
    end.
            
    
    
    
    