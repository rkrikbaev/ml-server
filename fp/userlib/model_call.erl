%%-----------------------------------------------------------------
%% Project: Faceplate / model service (HTTP 2-phase: request/response)
%%-----------------------------------------------------------------
-module(model_call).

-include("fp.hrl").

-export([
    % {ok, EncodedJson} | {error, Reason}
    request/2,
    % ok | {error, Reason}
    response/2,
    decode_points/1
]).

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

    case safe_read_fields(ModelPath, Fields) of
        {ok, R} ->
            Archives = maps:get(<<"model_input">>, R, []),
            Step0   = maps:get(<<"model_input_granularity">>, R, 3600), % сек
            InWin0  = maps:get(<<"model_input_range">>, R, 24),          % часы
            OutWin0 = maps:get(<<"model_output_range">>, R, 24),         % часы

            StepMs = ensure_ms(Step0),
            InWin  = ensure_int(InWin0, 24),
            OutWin = ensure_int(OutWin0, 24),

            ?LOGDEBUG("Select...", []),
            SeriesList0 = [ select(InWin, StepMs, A) || A <- Archives ],

            %% >>> применяем трансформер, если задан
            SeriesList = transform_series(Transform, SeriesList0),
            ?LOGDEBUG("Series list: ~p", [SeriesList]),
            case lists:partition(fun is_list/1, SeriesList) of
                {_Good, []} ->
                    case request_body(ModelPath, OutWin, StepMs, transform_struct(SeriesList)) of
                        {ok, Body} ->
                            {ok, Body};
                        {error, Why1} ->
                            {error, Why1}
                    end;
                {_Good, Bad} ->
                    ?LOGERROR("select failed for some archives: ~p", [Bad]),
                    {error, {select_failed, Bad}}
            end;

        {error, E} ->
            ?LOGERROR("model_service: read_fields failed: ~p", [E]),
            {error, E}
    end.


%%=================================================================
%% API: Step 2 — handle response and write to archive
%%  OutArchive задаёт внешний агент при вызове этой функции.
%%=================================================================
response(DataPoints, OutArchive) ->
    case transform_dataset(DataPoints) of
        {ok, Points} ->
            case commit(Points, OutArchive) of
                {ok, _Meta} ->
                    fp:log(debug, "model_service: wrote ~p points to ~p",
                           [length(Points), OutArchive]),
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
safe_read_fields(Path, Fields) ->
    try
        {ok, fp_db:read_fields(fp_db:open(Path), Fields)}
    catch
        Class:Reason:Stack ->
            ?LOGDEBUG("safe_read_fields() error: ~p ~p ~p", [Class, Reason, Stack]),
            {error, {Class, Reason}}
    end.

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

ensure_int(V, Default) when is_integer(V) -> V;
ensure_int(V, _Default) when is_float(V)  -> round(V);
ensure_int(V, Default) when is_binary(V) ->
    case catch binary_to_integer(V) of
        I when is_integer(I) -> I;
        _ -> Default
    end;
ensure_int(V, Default) when is_list(V) ->
    case catch list_to_integer(V) of
        I when is_integer(I) -> I;
        _ -> Default
    end;
ensure_int(_, Default) -> Default.

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

        fp:log(debug, "delete range From=~p To=~p", [From, To]),
        fp_ts:delete_period(project, [Archive], From, To),
        ?LOGDEBUG("data was deleted period from: ~p, to: ~p",[From, To]),
        R = fp_archive:insert_values(Archive, Data),
        ?LOGDEBUG("commit response: ~p", [R]),
        ?LOGDEBUG("written points: ~p", [length(Data)])
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
    ?LOGDEBUG("Series L: ~p", [ListOfSeries]),
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
