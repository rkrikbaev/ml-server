
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
    on_cycle/1,
    load_model_settings/2
  ]).
  

on_create(_Object)->
    ok.

on_edit( Object )->
    ?LOGINFO("prototypes/model_control:on_edit"),
    fp_util:check_changes(Object, [
        {fun load_model_settings/1, [<<"model_name">>, <<"model_edit_trigger">>]},
        {fun execute_model/1, [<<"run_task">>]},
        {fun load_data/1, [<<"output_data">>]}
        
    ]),
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
    project_model_service:run_task(Object).
    
load_model_settings(Object)->
    ?LOGINFO("model_control load_model_settings"),
    {ok, Name} = fp_db:read_field(Object, <<".name">>),
    try
        case fp_db:read_field(Object, <<"model_name">>) of 
            {ok, ModelNameID} -> 
                ?LOGINFO("Load data from this model ~p in this model control ~p", [ModelNameID, Name]),
                load_model_settings(Object, ?OBJECT(ModelNameID));
            {ok, none} -> 
                ?LOGINFO("This modal control ~p does't have a worker", [Name]),
                ok
        end
    catch
        _:Error -> ?LOGERROR("model settings read error ~p",[ Error ])
    end.
    
load_model_settings(Object, CatalogObject)->
    #{
        <<"model_input">> := ModelInput, 
        <<"input_range">> := InputRange, 
        <<"output_range">> := OutputRange, 
        <<"model_port">> := ModelPort, 
        <<"model_host">> := ModelHost,
        <<"model_output">> := ModelOutput,
        <<"model_path">> := ModelPath,
        <<"step">> := Step
    } = fp_db:read_fields(CatalogObject, [<<"model_input">>, <<"input_range">>, <<"output_range">>, <<"model_port">>, <<"model_host">>, <<"model_output">>, <<"model_path">>, <<"step">>]),
    fp_db:edit_object(Object, #{
        <<"model_input">> => ModelInput, 
        <<"model_input_range">> => InputRange, 
        <<"model_output_range">> => OutputRange, 
        <<"model_port">> => ModelPort,
        <<"model_host">> => ModelHost,
        <<"model_output">> => ModelOutput,
        <<"model_path">> => ModelPath,
        <<"model_input_granularity">> => Step
    }),
    ok.

load_data(Object)->
    #{ <<"output_data">>:=BinaryString, <<"model_output">>:=Archive } = fp_db:read_fields(Object, [<<"output_data">>,<<"model_output">>]),
    Data = binary_to_term(BinaryString),
    case project_model_service:write_to_db(Data, Archive) of
        {ok,[DataAsBinString,From,To]}->
            ?LOGINFO( "Write to DB success",[] );
        {error,_}->
            ?LOGERROR( "Write to DB failed", [] )
    end.
            
    
    
    
    