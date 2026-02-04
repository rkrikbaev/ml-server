
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
    on_edit/1
  ]).
  
-export([
    on_cycle/2
  ]).
  
-export([
    request/1,
    response/2
]).

-export([
    sync_archives/3
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
    
on_cycle( FolderPath, HorizonKey )->
    Query = {'ANDNOT',
        {'AND',[
            {<<".pattern">>,'=',?OID(<<"/root/FP/prototypes/model_control/fields">>)},
            {<<".fp_path">>,'LIKE', <<"^", FolderPath/binary>>},
            {<<"is_prototype">>, '=', false}
        ]},
        {<<"disabled">>,'=',true}
    },
    
    fp_kegoc_util:on_cycle(Query,[
        fun(Object) -> execute_model(Object, HorizonKey) end
    ]).

execute_model(Object, HorizonKey)->
    #{ <<"configuration">>:=ConfigurationString } = fp_db:read_fields(Object, [<<"configuration">>]),
    Configuration = json:decode(ConfigurationString),
    case select_maps_by_value(Configuration, <<"name">>, HorizonKey) of 
        [HorizonConfiguration] ->
            % NewState = case State of 
            %     none -> 
            %         0;
            %     _ ->
            %         (fp_util:coerce_value(integer, State) + 1) rem 10
            % end,
            % ?LOGDEBUG("State: ~p, NewState: ~p", [State, NewState]),
            
            fp_db:edit_object(
                Object,
                maps:merge(
                    #{
                        <<"execute">> => ?TS
                    },
                    HorizonConfiguration
                )
            ),
            
            {ok, none};
        _ ->
            ?LOGERROR("Wrong key HorizonKey: ~p for Configuration: ~p", [HorizonKey, Configuration]),
            {error, wrong_key}
    end.

select_maps_by_value(MapsList, Key, TargetValue) ->
    [Map || Map <- MapsList, maps:get(Key, Map, undefined) == TargetValue].

load_data(Object)->
    ObjPath = fp_db:to_path(Object),
    ArchivePath = <<ObjPath/binary, "/archives/out_value">>,

    #{ <<"output_data">>:=BinaryString} = fp_db:read_fields(Object, [<<"output_data">>]),
    
    Data = binary_to_term(BinaryString),
    case commit(Data, ArchivePath) of
        {ok,[DataAsBinString,From,To]}->
            ?LOGDEBUG( "Write to DB success",[] );
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
request(#{ "path" := Path }) ->
    request(Path);
request(Path) when is_binary(Path) ->
    fp:log(debug, "Run the task...", []),
    fp:log(debug, "Model object path: ~p", [Path]),
    
    Fields = [ 
        <<"input">>,
        <<"step">>, 
        <<"input_range">>, 
        <<"output_range">>, 
        <<"model_path">>,
        <<"transformation">>
    ],
                
    case fp_db:read_fields(fp_db:open(Path), Fields) of
        Config when is_map(Config) -> 
            process_request(Config);
        Error ->
            ?LOGERROR("Failed to read fields for request at ~p: ~p", [Path, Error]),
            {error, read_failed}
    end.

%%=================================================================
%% API: Step 2 — handle response and write to model's archive
%%=================================================================

%% 1. Точка входа, если аргументы упакованы в Map (как в логах fp_iot_client)
response(Data, #{"path" := ModelPath}) ->
    response(Data, ModelPath);

%% 2. Если данные пришли как Binary (JSON), декодируем их
response(ResponseBody, ModelPath) when is_binary(ResponseBody) ->
    ?LOGDEBUG("Decoding ResponseBody for path: ~p", [ModelPath]),
    case decode_points(ResponseBody) of
        {ok, Data} -> response(Data, ModelPath);
        {error, R} -> ?LOGERROR("Decode error: ~p", [R])
    end;

%% 3. Если данные — список (proplist), конвертируем в Map для единообразия
response(ResponseList, ModelPath) when is_list(ResponseList), is_binary(ModelPath) ->
    ?LOGDEBUG("ResponseList: ~p", [ResponseList]),
    response(maps:from_list(ResponseList), ModelPath);

%% 4. Основной обработчик (когда данные уже Map, а путь — Binary)
response(DataMap, ModelPath) when is_map(DataMap), is_binary(ModelPath) ->
    ?LOGDEBUG("Processing model response for: ~p", [ModelPath]),
    ?LOGDEBUG("DataMap: ~p", [DataMap]),
    case fp_db:read_fields(fp_db:open(ModelPath), [<<"name">>]) of
        ModelConfig when is_map(ModelConfig) ->
            ArchiveName = maps:get(<<"name">>, ModelConfig, <<"out_value">>),
            ArchiveMountPointPath = <<ModelPath/binary, "/archives/", ArchiveName/binary>>,
            
            %% Извлекаем поля из ответа. Используем дефолтные значения, чтобы избежать краша.
            DataPoints  = maps:get(<<"task_output">>, DataMap, []),
            TaskStatus  = maps:get(<<"task_status">>, DataMap, <<"ERROR">>),
            TaskMessage = maps:get(<<"task_message">>, DataMap, <<"No message">>),
            TaskState = maps:from_list(maps:get(<<"state">>, DataMap )),
            ?LOGDEBUG("TaskState: ~p", [TaskState]),
            case transform_dataset(DataPoints) of
                {ok, []} -> 
                    ?LOGWARNING("No valid data points to write for ~p", [ModelPath]);
                {ok, Points} ->
                    case commit(Points, ArchiveMountPointPath) of
                        {ok, _} -> 
                            ?LOGDEBUG("Model ~p: wrote ~p points", [ArchiveMountPointPath, length(Points)]);
                        {error, Reason} -> 
                            ?LOGERROR("Commit failed for ~p: ~p", [ModelPath, Reason])
                    end;
                {error, E1} ->
                    ?LOGERROR("Dataset transformation failed: ~p", [E1])
            end,

            %% Обновляем статус в объекте модели
            fp_db:edit_object(fp_db:open(ModelPath), #{
                <<"task_status">> => TaskStatus,
                <<"task_message">> => TaskMessage,
                <<"task_updated">> => list_to_binary(utc_time()),
                <<"state">> => iolist_to_binary(json:encode(TaskState))
            });

        Error ->
            ?LOGERROR("Could not read model fields at ~p: ~p", [ModelPath, Error])
    end.

process_request(#{
                    <<"input">>:=ArchivesAsModelInput,
                    <<"step">>:=StepBetweenPoints,
                    <<"input_range">>:=InputDataWindowRange,
                    <<"output_range">>:=OutputDataWindowRange,
                    <<"model_path">>:=ModelPath,
                    <<"transformation">>:=Function
                })->
    
    case select(InputDataWindowRange * ?HOUR_SEC * ?MSEC, StepBetweenPoints * ?MSEC, ArchivesAsModelInput) of
        {ok,SeriesDataMap} when is_map(SeriesDataMap)-> 
            SeriesDataMapValuesList = transform_struct(ArchivesAsModelInput, SeriesDataMap),
            TransformedDataList = 
                case Function of
                    none -> 
                        ?LOGDEBUG("Transformation skipped: Transform function is 'none'", []),
                        SeriesDataMapValuesList;
                    _ -> 
                        ?LOGDEBUG("Applying transformation: ~p",[Function]),
                        [ transform_series(Function, Series) || Series <-SeriesDataMapValuesList]
                end,
            case lists:partition(fun is_list/1, TransformedDataList) of
                {_Good, []} ->
                    request_body(ModelPath, OutputDataWindowRange, StepBetweenPoints * ?MSEC, TransformedDataList);
                {_Good, Bad} ->
                    ?LOGERROR("select failed for some archives: ~p", [Bad]),
                    {error, {select_failed, Bad}}
            end;
        {R1, E1} ->
            ?LOGERROR("Error read archives: ~p:~p", [R1,E1])
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
        From  = Now - InputWindow,
        To    = From + 2 * InputWindow,
        lists:seq(From, To - Step, Step).

% TO DO
% Mode: 1 - past, 2 - past + future
ts_series(InputWindow,Step,0)->
    To = ?TS,
    From  = To - InputWindow,
    lists:seq(From, To - Step, Step);
ts_series(InputWindow,Step,1)->
    To = ?TS + InputWindow,
    From  = ?TS - InputWindow,
    lists:seq(From, To - Step, Step);
ts_series(_,_,_)->
    To = ?TS,
    From  = ?TS - 24 * 3600 * 1000,
    Step = 3600 * 1000,
    lists:seq(From, To - Step, Step).

transform_dataset(Series) when is_list(Series) ->
    try
        T = [ {convert_timestamp_to_ms(Ts), V}
              || [Ts, V, _Q] <- Series ],
        {ok, T}
    catch
        _:Err ->
            {error, {bad_dataset, Err}}
    end.

request_body(ModelPath, OutputWindow, Step, Series) ->
    TaskId = int_to_binary_string(erlang:system_time()),
    try
        Payload = [
            {<<"task_id">>,    TaskId},
            {<<"period">>,     OutputWindow},
            {<<"step">>,       Step},
            {<<"task_input">>, Series},
            {<<"model_path">>, ModelPath}
        ],
        ?LOGINFO("Payload ~p",[Payload]),
        %% Возвращаем просто результат кодирования (Binary)
        jsx:encode([Payload])
    catch
        _:Error ->
            ?LOGERROR("request_body error: ~p", [Error]),
            %% Возвращаем пустую строку или ошибку в формате, который не положит клиент
            <<>> 
    end.

%% ---- Response decoding ----

decode_points(Bin) ->
    case catch jsx:decode(Bin) of
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
    ?LOGDEBUG("Archive: ~p",[Archive]),
    try
        {From, _} = hd(Data),
        {To, _} = lists:last(Data),
        % ?LOGDEBUG("Delete range From=~p To=~p", [From, To]),
        ArchiveOID = ?OID( Archive ),
        DBName = fp_archive:get_storage(ArchiveOID),
        % ?LOGDEBUG("DBName: ~p", [DBName]),
        fp_ts:delete_period(project_ts_database, [ArchiveOID], From, To),
        % ?LOGDEBUG("Data was deleted period from: ~p, to: ~p",[From, To]),
        ?LOGDEBUG("Data: ~p",[Data]),
        fp_archive:insert_values(Archive, Data),
        ?LOGDEBUG("Data commited..."),
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

%% 
%% ---------- Трансформация ----------
%% 
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
        [ [T, V, Q] || [T, V, Q] <- maps:get(K, SeriesDataMap) ]
        || K <- Keys
    ].

% 
% Синхронизация архивов
% 
sync_archives(FolderPath, Replica, Seconds)->
    Query = {'ANDNOT',
        {'AND',[
            {<<".pattern">>,'=',?OID(<<"/root/FP/prototypes/model_control/fields">>)},
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
