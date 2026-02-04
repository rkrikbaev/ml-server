%%-----------------------------------------------------------------
%% Project: Faceplate / model service (HTTP 2-phase: request/response)
%%-----------------------------------------------------------------
-module(fp_userlib_model).

-include("fp.hrl").

-export([
    % {ok, EncodedJson} | {error, Reason}
    request/2,
    % ok | {error, Reason}
    response/2
]).

-define(MSEC,1000).

%%=================================================================
%% API: Step 1 — build request
%%=================================================================

%% Второй аргумент используем как трансформер:
%% - none                       -> без изменений
%% - fun(Series) -> Series      -> анонимная функция
%% - atom()                     -> локальная функция модуля
%% - {Module, Function}         -> M:F(Series)
request(ModelPath, Transform) ->

    fp:log(debug, "Run the task...", []),
    fp:log(debug, "ModelPath: ~p", [ModelPath]),
    
    Fields = [<<"model_input">>, <<"model_input_granularity">>, <<"model_input_range">>, <<"model_output_range">>],
    case fp_db:read_fields(fp_db:open(ModelPath),Fields) of
        ModelConfig when is_map(ModelConfig)->
            ?LOGDEBUG("ModelConfig: ~p", [ModelConfig]),
            ArchivesAsModelInput = maps:get(<<"model_input">>, ModelConfig, []),
            StepBetweenPoints   = maps:get(<<"model_input_granularity">>, ModelConfig, 3600), % сек
            InputDataWindowRange  = maps:get(<<"model_input_range">>, ModelConfig, 48),          % часы
            OutputDataWindowRange = maps:get(<<"model_output_range">>, ModelConfig, 24),
            SeriesList0 = [ select(InputDataWindowRange, StepBetweenPoints * ?MSEC, A) || A <- ArchivesAsModelInput ],
            DataList = transform_series(Transform, SeriesList0),
            case lists:partition(fun is_list/1, DataList) of
                {_Good, []} ->
                    case request_body(ModelPath, OutputDataWindowRange, StepBetweenPoints * ?MSEC, transform_struct(DataList)) of
                        {ok, Body} ->
                            {ok, Body};
                        {error, Why1} ->
                            {error, Why1}
                    end;
                {_Good, Bad} ->
                    ?LOGERROR("select failed for some archives: ~p", [Bad]),
                    {error, {select_failed, Bad}}
            end;
        {R, E0} ->
            ?LOGERROR("model_service: read_fields failed: ~p:~p", [R,E0])
    end.


%%=================================================================
%% API: Step 2 — handle response and write to archive
%%  OutArchive задаёт внешний агент при вызове этой функции.
%%=================================================================
response(ResponseDataList,MountPoint) ->

    ?LOGDEBUG("Response Data List ~p",[ResponseDataList]),
    DataMap = maps:from_list(ResponseDataList),
    
    #{<<"task_output">>:=DataPoints} = DataMap,

    MountPoint = <<"/root/FP/PROJECT/test/model_control/model/archives/out_value">>,
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
        {error, Why} ->
            ?LOGERROR("transform_dataset failed: ~p", [Why]),
            {error, Why}
    end.

%%=================================================================
%% Helpers
%%=================================================================

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

select(InputWindowHours, StepMs, Archive) ->
    ?LOGDEBUG("select Archive: ~p",[Archive]),
    try
        Now   = timestamp(),
        Base  = (Now div StepMs) * StepMs,
        From  = Base - (InputWindowHours * 3600000),
        To    = Base + (InputWindowHours * 3600000),
        
        ?LOGDEBUG("model_service: From=~p To=~p Step=~p", [From, To, StepMs]),
        ?LOGDEBUG("model_service: Archive: ~p", [fp_db:to_path(Archive)]),
        
        Ts = lists:seq(From + StepMs, To, StepMs),
        [ fp_archive:get_point(Archive, T1) || T1 <- Ts ]
        
    catch
        Class:Reason ->
            ?LOGERROR("select error: ~p:~p", [Class, Reason]),
            {error, {read_failure, Reason}}
    end.

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
            {<<"model_path">>, none}
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
transform_series(Transform, SeriesList) ->
    [ transform_one(Transform, S) || S <- SeriesList ].

transform_one(Transform, Series) when is_list(Series) ->
    case run_transform(Transform, Series) of
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

transform_struct(ListOfSeries) when is_list(ListOfSeries) ->
    [
        [
            % The inner list comprehension iterates over the tuples in one series
            [Ts, V] 
            || Series <- ListOfSeries,  % Unpack the outer list (if multiple series)
               {Ts, V} <- Series        % Unpack the tuples into lists
        ]
    ];

transform_struct(none) ->
    [].

