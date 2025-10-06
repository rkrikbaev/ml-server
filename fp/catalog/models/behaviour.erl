
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
-module(fp_prototype_models).

-include("fp.hrl").
  
%% ------------------------ ECOMET ------------------------------
-export([
    on_create/1,
    on_delete/1,
    on_edit/1
  ]).
  
%% ------------------------ ECOMET ------------------------------
on_create(Object)->
    add_model_for_worker(Object),
    ok.
    
on_edit(Object)->
    ?LOGINFO("catalog/models:on_edit"),
    fp_util:check_changes(Object, [
        {fun edit_data_for_worker/1, [
        <<"workers">>, 
        <<"input_range">>, 
        <<"model_input">>, 
        <<"model_path">>, 
        <<"output_range">>,
        <<"settings">>,
        <<"step">>,
        <<"model_port">>,
        <<"model_host">>
        ]}
    ]),
    ok.
on_delete(Object)->
    delete_model_for_worker(Object),
    ok.
  
%% ------------------------ API ------------------------------
add_model_for_worker(Object)->
    {ok, ObjectPath} = fp_db:read_field(Object, <<".path">>),
    {ok, Worker} = fp_db:read_field(Object, <<"worker">>),
    
    try ?OBJECT(Worker) of WorkerObject ->
        fp_db:edit_object(WorkerObject, #{<<"model_name">> => ObjectPath}),
        ?LOGINFO("Workers model_name is edit ~p", [Worker])
    catch
        _:Error -> {error, Error},
        ?LOGINFO("catalog/models:add_model_for_worker error: ~p", [Error])
    end,
    ok.
    
delete_model_for_worker(Object)->
    {ok, Worker} = fp_db:read_field(Object, <<"worker">>),
    try ?OBJECT(Worker) of WorkerObject ->
        fp_db:edit_object(WorkerObject, #{
            <<"model_name">> => none
        })
    catch
        _:Error -> {error, Error},
        ?LOGINFO("catalog/models:delete_model_for_worker error: ~p", [Error])
    end,
    ok.
  
edit_data_for_worker(Object) ->
    {ok, ObjectPath} = fp_db:read_field(Object, <<".path">>),
    {ok, Worker} = fp_db:read_field(Object, <<"worker">>),

    try ?OBJECT(Worker) of WorkerObject ->
        ?LOGINFO("catalog/models:edit_data_for_worker Worker = ~p", [Worker]),
        ?LOGINFO("Model is edit, edit object for ~p", [Worker]),
        
        fp_db:edit_object(WorkerObject, #{
            <<"model_name">> => ObjectPath,
            <<"model_edit_trigger">> => rand:uniform(256) - 1
        })
    catch
        _:Error -> {error, Error},
        ?LOGINFO("catalog/models:edit_data_for_worker error: ~p", [Error])
    end,
    ok.

    