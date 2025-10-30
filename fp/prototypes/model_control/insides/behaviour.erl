
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
  
-export([
    request/2,
    response/2
]).


on_create(_Object)->
    ok.

on_edit( Object )->
    fp_util:check_changes(Object, [
        {fun load_data/1, [<<"output_data">>]},
        {fun update_url/1, [<<"host">>, <<"port">>]}
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
    %% Extract connection path from object
    ObjPath = fp_db:to_path(Object),
    ConnectionPath = <<ObjPath/binary, "/http_client_connection">>,

    %% Set trigger
    fp_db:edit_object(
        fp_db:open(ConnectionPath),
        #{
            <<"trigger">> => true
        }
    ).

load_data(Object)->
    ObjPath = fp_db:to_path(Object),
    ArchivePath = <<ObjPath/binary, "/archives/out_value">>,

    #{ <<"output_data">>:=BinaryString} = fp_db:read_fields(Object, [<<"output_data">>]),
    
    Data = binary_to_term(BinaryString),
    case commit(Data, ArchivePath) of
        {ok,[DataAsBinString,From,To]}->
            ?LOGINFO( "Write to DB success",[] );
        {error,_}->
            ?LOGERROR( "Write to DB failed", [] )
    end.

update_url(Object)->
    ObjPath = fp_db:to_path(Object),
    ConnectionPath = <<ObjPath/binary, "/http_client_connection">>,

    #{ <<"host">>:=Host, <<"port">>:=Port } = fp_db:read_fields(Object, [<<"host">>, <<"port">>]),
    
    fp_db:edit_object(
        fp_db:open(ConnectionPath),
        #{
            <<"url">> => <<"http://", Host/binary, ":", Port/binary, "/predict">>
        }
    ).
    
    
%%=================================================================
%% API: Send-Receive data from/to model
%%=================================================================

-define(MSEC,1000).
-define(HOUR_SEC,3600).

%%=================================================================
%% API: Step 1 — build request
%%=================================================================

%% Второй аргумент используем как трансформер:
%% - none                       -> без изменений
%% - fun(Series) -> Series      -> анонимная функция
%% - atom()                     -> локальная функция модуля
%% - {Module, Function}         -> M:F(Series)
request(ModelControlPath, Transform) ->

    fp:log(debug, "Run the task...", []),
    fp:log(debug, "ModelPath: ~p", [ModelControlPath]),
    
    Fields = [<<"input">>, <<"step">>, <<"input_range">>, <<"output_range">>, <<"model_path">>],
    case fp_db:read_fields(fp_db:open(ModelControlPath),Fields) of
        ModelConfig when is_map(ModelConfig)->
            ?LOGDEBUG("ModelConfig: ~p", [ModelConfig]),
            ArchivesAsModelInput = maps:get(<<"input">>, ModelConfig, []),
            StepBetweenPoints   = maps:get(<<"step">>, ModelConfig, 3600), % сек
            InputDataWindowRange  = maps:get(<<"input_range">>, ModelConfig, 48),          % часы
            OutputDataWindowRange = maps:get(<<"output_range">>, ModelConfig, 24),
            ModelPath = maps:get(<<"model_path">>, ModelConfig, 24),
            % SeriesList0 = [ select(InputDataWindowRange, StepBetweenPoints * ?MSEC, A) || A <- ArchivesAsModelInput ],
            case select(InputDataWindowRange * ?HOUR_SEC * ?MSEC, StepBetweenPoints * ?MSEC, ArchivesAsModelInput) of
                {ok,SeriesDataMap} when is_map(SeriesDataMap)-> SeriesDataMap,
                    SeriesDataMapValuesList = transform_struct(ArchivesAsModelInput, SeriesDataMap),
                    ?LOGDEBUG("Series Data Map Values List: ~p",[SeriesDataMapValuesList]),
                    TransformedDataList = [ transform_series(Transform, Series) || Series <-SeriesDataMapValuesList],
                    ?LOGDEBUG("Transformed Data List: ~p",[TransformedDataList]),
                    case lists:partition(fun is_list/1, TransformedDataList) of
                        {_Good, []} ->
                            case request_body(ModelPath, OutputDataWindowRange, StepBetweenPoints * ?MSEC, TransformedDataList) of
                                {ok, Body} ->
                                    {ok, Body};
                                {error, Why1} ->
                                    {error, Why1}
                            end;
                        {_Good, Bad} ->
                            ?LOGERROR("select failed for some archives: ~p", [Bad]),
                            {error, {select_failed, Bad}}
                    end;
                {R1, E1} ->
                    ?LOGERROR("Error read archives: ~p:~p", [R1,E1])
            end;
        {R0, E0} ->
            ?LOGERROR("Error when read fields: ~p:~p", [R0,E0])
    end.

%%=================================================================
%% API: Step 2 — handle response and write to model's archive
%% ModelPath задаёт внешний агент при вызове этой функции.
%%=================================================================
%% Clause to handle raw binary response (e.g., from an HTTP client)
response(ResponseBody, ModelPath) when is_binary(ResponseBody) ->
    ?LOGDEBUG("Response Body (binary) %p",[ResponseBody]),
    case decode_points(ResponseBody) of
        {ok, ResponseDataList} ->
            response(ResponseDataList, ModelPath);
        {error, Reason} ->
            ?LOGERROR("JSON decoding failed: %p", [Reason]),
            {error, Reason}
    end;

%% Original clause to handle decoded list of tuples (or internal calls)
response(ResponseDataList,ModelPath) when is_list(ResponseDataList) ->
    MountPoint = ?OID(<<ModelPath/binary, "/archives/out_value">>),
    
    ?LOGDEBUG("Response Data List %p",[ResponseDataList]),
    DataMap = maps:from_list(ResponseDataList),

    %% Handle task_output
    case DataMap of
        %% Handle case where task_output is present but empty
        #{<<"task_output">>:=[]} ->
            ?LOGWARNING("No data returned from model in task_output"),
            ok;

        %% Handle case where task_output has data
        #{<<"task_output">>:=DataPoints} ->
            case transform_dataset(DataPoints) of
                {ok, Points} ->
                    case commit(Points, MountPoint) of
                        {ok, _Meta} ->
                            fp:log(debug, "model_service: wrote ~p points to ~p",
                                [length(Points), MountPoint]),
                                ok;
                        {error, Reason} ->
                            ?LOGERROR("commit failed: ~p", [Reason]),
                            {error, Reason}
                    end;
                {error, E1} ->
                    ?LOGERROR("transform_dataset failed: ~p", [E1]),
                    {error, E1}
            end;
            
        %% Catch-all for missing task_output or unexpected map structure
        _ ->
            ?LOGERROR("Response map missing task_output: %p", [DataMap]),
            {error, missing_task_output}
    end,

    %% Handle task info (status and message)
    case DataMap of
        %% Handle case where all the rest of task info has data
        #{<<"task_status">>:=TaskStatus, <<"task_message">>:=TaskMessage} ->
            fp_db:edit_object(
                fp_db:open(ModelPath),
                #{
                    <<"task_status">> => TaskStatus,
                    <<"task_message">> => TaskMessage,
                    <<"task_updated">> => list_to_binary(utc_time())
                }
            );
        %% Catch-all for missing task info or unexpected map structure
        _ ->
            ?LOGERROR("Response map missing task info: %p", [DataMap]),
            {error, missing_task_info}
    end.

%%=================================================================
%% Helpers
%%=================================================================

utc_time() ->
    {{Year, Month, Day}, {Hour, Minute, Second}} = calendar:universal_time(),
    FormattedYear = Year rem 100, % Get last two digits of the year
    io_lib:format("~2..0B/~2..0B/~2..0B ~2..0B:~2..0B:~2..0B",
                  [FormattedYear, Month, Day, Hour, Minute, Second]).

ensure_ms(V) ->
    case V of
        N when is_integer(N) -> N * 1000;
        N when is_float(N)   -> round(N * 1000);
        B when is_binary(B)  ->
            case catch binary_to_integer(B) of
                I when is_integer(I) -> I * 1000;
                _ -> 3600000
            end;
        L when is_list(L) ->
            case catch list_to_integer(L) of
                I when is_integer(I) -> I * 1000;
                _ -> 3600000
            end;
        _ -> 3600000
    end.

timestamp() ->
    erlang:system_time(millisecond).

select(InputWindow, Step, ArchivesList) ->
    ?LOGDEBUG("Archives List: ~p",[ArchivesList]),
    try
        TsList = ts_list(InputWindow, Step),
        fp_userlib_archive_handler:get_points(ArchivesList, TsList)
    catch
        Class:Reason ->
            ?LOGERROR("select error: ~p:~p", [Class, Reason]),
            {error, {read_failure, Reason}}
    end.

ts_list(InputWindow, Step)->
        Now   = timestamp(),
        Base  = (Now div Step) * Step,
        From  = Base - InputWindow,
        To    = Now,
        lists:seq(From, To - Step, Step).

transform_dataset(Series) when is_list(Series) ->
    try
        T = [ {convert_timestamp_to_ms(Ts), V}
              || [Ts, V] <- Series,
                 V =/= none, V =/= null, V =/= undefined ],
        {ok, T}
    catch
        _:Err ->
            {error, {bad_dataset, Err}}
    end.

request_body(ModelPath, OutputWindow, Step, Series) ->
    TaskId = int_to_binary_string(erlang:system_time()),
    try
        {ok, [
            {<<"task_id">>,    TaskId},
            {<<"period">>,     OutputWindow},
            {<<"step">>,       Step},
            {<<"task_input">>, Series},
            {<<"model_path">>, ModelPath}
        ]}
    catch
        _:Error ->
            ?LOGERROR("request_body error: ~p", [Error]),
            {error, failed_to_construct_body}
    end.

%% ---- Response decoding ----

decode_points(Bin) ->
    case catch jsx:decode(Bin,[return_maps]) of
        {'EXIT', Reason} ->
            {error, {bad_json, Reason}};
        Points ->
            {ok, Points}
    end.

to_int_ms(Ts) when is_integer(Ts) -> convert_timestamp_to_ms(Ts);
to_int_ms(Ts) when is_float(Ts)   -> convert_timestamp_to_ms(round(Ts));
to_int_ms(Ts) when is_binary(Ts)  ->
    case catch binary_to_integer(Ts) of
        I when is_integer(I) -> convert_timestamp_to_ms(I);
        _ ->
            case catch binary_to_float(Ts) of
                F when is_float(F) -> convert_timestamp_to_ms(round(F));
                _ -> error
            end
    end;
to_int_ms(_) -> error.

to_number(V) when is_integer(V) -> V;
to_number(V) when is_float(V)   -> V;
to_number(<<"null">>)           -> error;
to_number(null)                 -> error;
to_number(B) when is_binary(B)  ->
    case catch binary_to_integer(B) of
        I when is_integer(I) -> I;
        _ ->
            case catch binary_to_float(B) of
                F when is_float(F) -> F;
                _ -> error
            end
    end;
to_number(_) -> error.

%% ---- Writing back ----

commit(Data, Archive) ->
    ?LOGDEBUG("Data: ~p",[Data]),
    ?LOGDEBUG("Archive: ~p",[Archive]),
    try
        {From, _} = hd(Data),
        {To,   _} = lists:last(Data),

        ?LOGDEBUG("Delete range From=~p To=~p", [From, To]),

        ArchiveOID = ?OID( Archive ),
        DBName = fp_archive:get_storage(ArchiveOID),
        
        ?LOGDEBUG("DBName: ~p", [DBName]),
        ?LOGDEBUG("ArchiveOID: ~p", [ArchiveOID]),
        
        % Delete the existing data points in the given range
        % TODO: should we provide DBName instead of project_ts_database?
        fp_ts:delete_period(project_ts_database, [ArchiveOID], From, To),
        
        ?LOGDEBUG("Data was deleted period from: ~p, to: ~p",[From, To]),
        fp_archive:insert_values(Archive, Data),
        {ok, none}
    catch
        Class:Reason ->
            ?LOGERROR("commit error: ~p:~p", [Class, Reason]),
            {error, Reason}
    end.

%% ---- Misc ----

int_to_binary_string(Int) when is_integer(Int) ->
    list_to_binary(io_lib:format("~p", [Int])).

convert_timestamp_to_ms(Timestamp) when Timestamp < 1_000_000_000_000_000 ->
    Timestamp; % миллисекунды
convert_timestamp_to_ms(Timestamp) when Timestamp < 1_000_000_000_000_000_000 ->
    Timestamp div 1_000; % микросекунды -> мс
convert_timestamp_to_ms(Timestamp) when Timestamp < 1_000_000_000_000_000_000_000 ->
    Timestamp div 1_000_000. % наносекунды -> мс


%% ---------- Трансформация ----------

transform_series(none, SeriesList) ->
    SeriesList;
transform_series(Fun, SeriesList) ->
    [ transform_one(Fun, S) || S <- SeriesList ].

transform_one(Fun, Series) when is_list(Series) ->
    case run_transform(Fun, Series) of
        {ok, S1} when is_list(S1) -> S1;
        S1 when is_list(S1)       -> S1;
        {error, Reason} ->
            ?LOGWARNING("Transform failed (~p). Keep original series.", [Reason]),
            Series
    end.

%% Универсальный вызов трансформера над одной серией [{Ts,Val}] или [[Ts,Val]]
run_transform(Fun, Series) when is_function(Fun, 1) ->
    try Fun(Series) of
        {ok, D} -> {ok, D};
        D       -> {ok, D}
    catch C:R -> {error, {C,R}}
    end;
run_transform({M, F}, Series) when is_atom(M), is_atom(F) ->
    try erlang:apply(M, F, [Series]) of
        {ok, D} -> {ok, D};
        D       -> {ok, D}
    catch C:R -> {error, {C,R}}
    end;
run_transform(A, Series) when is_atom(A) ->
    %% считаем, что функция в этом же модуле
    run_transform({?MODULE, A}, Series);
run_transform(_, Series) ->
    {ok, Series}.  %% на всякий случай no-op

transform_struct(Keys, SeriesDataMap)->
    %% Сохраняя тот же порядок, что и в Keys
    [ 
        [ [T, V] || [T, V, _QI] <- maps:get(K, SeriesDataMap) ]
        || K <- Keys
    ].
