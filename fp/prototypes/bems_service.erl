
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

-module(fp_proto_bems_service).

-include("fp.hrl").

-export([
    on_create/1,
    on_delete/1,
    on_edit/1
  ]).
  
-export([
    run/1
  ]).
  
-define(URL_DATA, "https://bems.kegoc.kz/integration/api/v1/integration/plans").
-define(URL_TOKEN, "https://id.kegoc.kz/realms/sbre-prod/protocol/openid-connect/token").

-define(USER_NAME,"scada_system").
-define(PASSWORD,"QWE@#kegsCaDa90").
-define(CLIENT_SECRET,"tJpO0k832VdeePNm7qhq1fvHuYKhVMsp").
-define(BEMS_UTC_OFFSET_HOURS,1).

on_create(_Object)->
  ok.
on_edit(_Object)->
  ok.
on_delete(_Object)->
  ok.

                
% -----------------------------------------------------------------------------+
%                                   API                                        +
% -----------------------------------------------------------------------------+
  
run(IsTomorrow)->
    ?LOGDEBUG("Start..."),
    Hours = lists:seq(0, 23),
    try
        Ts = erlang:system_time() div 1000000,
        Content = case find_items() of
                {ok, {_, O}} ->
                    O;
                _ ->
                    []
            end,
        % Запрос по объектам. Нужно вытащить все субьекты и их коды
        OIDs = [ OID || [OID, _] <- Content],
        Objects = [ Code || [_, Code] <- Content],
        ?LOGDEBUG("Objects ~p",[Objects]),
        case request_token() of
            {ok, Token} ->
                %% Выполняем запрос с токеном
                % ?LOGDEBUG("Request Token ~p",[Token]),
                case request_data(Token, Hours, Objects, IsTomorrow) of
                    {ok, Responses} ->
                        ?LOGDEBUG("Responses: ~p~n", [Responses]),
                        try
                            lists:foreach(fun(Response) ->
                                case process_data(OIDs, Objects, Response) of 
                                    ok -> ok;
                                    {error, Reason} ->
                                        ?LOGWARNING("Error when process data: ~p", [Reason])
                                end
                            end, Responses)
                        catch
                            E:R->?LOGWARNING("Error when process data: ~p, ~p", [E,R])
                        end;
                    {error, Reason} ->
                        ?LOGWARNING("Fail to get data: ~p", [Reason]),
                        {error, Reason}
                end;
            {error, Reason} ->
                ?LOGWARNING("Fail to get token: ~p", [Reason])
        end
    catch
        ClE:Error ->
            ?LOGERROR("Failed to run BMS service: ~p, Error: ~p", [ClE,Error]),
            {error, {write_failure, Error}}
    end.

% -----------------------------------------------------------------------------+
%                               Internal functions                             +
% -----------------------------------------------------------------------------+      
request_token() ->
    ?LOGDEBUG("Request token..."),

    %% Формируем тело запроса
    Body = "grant_type=password&client_id=admin-cli&username="++?USER_NAME++"&password="++?PASSWORD++"&client_secret="++?CLIENT_SECRET++"&scope=openid",

    %% Заголовки запроса
    HTTPHeaders = [{"Content-Type", "application/x-www-form-urlencoded"}],
    HTTPRequest = {?URL_TOKEN, HTTPHeaders, "application/x-www-form-urlencoded", Body},
    
    ?LOGDEBUG("HTTP Request for token: ~p", [HTTPRequest]),

    %% Опции запроса
    % Options = [{timeout, 10000}], %% Тайм-аут 10 секунд
    Options = [],
    %% Выполняем запрос
    case httpc:request(post, HTTPRequest, [], Options) of
        %% Успешный ответ
        {ok, {{_, 200, _}, _Headers, ResponseBody}} ->
            ?LOGDEBUG("TokenResponse: ~s", [ResponseBody]),
            %% Парсим ответ
            BinaryBody = case is_binary(ResponseBody) of
                true -> ResponseBody;
                false -> list_to_binary(ResponseBody)
            end,
            case jsx:decode(BinaryBody, [return_maps]) of
                #{<<"access_token">> := Token} -> 
                    {ok, Token};
                _ -> 
                    {error, no_token_in_response}
            end;
        %% Ошибка выполнения HTTP-запроса
        {ok, {{_, StatusCode, _}, _Headers, ResponseBody}} ->
            ?LOGERROR("Ошибка: Статус ~p, Тело: ~s", [StatusCode, ResponseBody]),
            {error, {unexpected_status, StatusCode}};
        {error, Reason} ->
            ?LOGERROR("Ошибка соединения: ~p", [Reason]),
            {error, Reason}
    end.
    
request_data(Token, Hours, Objects, IsTomorrow) ->
    %% URL запроса
    ?LOGDEBUG("Request data..."),

    % Get local current datetime
    DateTimeLocal = calendar:universal_time_to_local_time(calendar:universal_time()),

    % Offset the date if IsTomorrow is true and extract date part
    {{CurrentYear, CurrentMonth, CurrentDay}, _} = 
        if IsTomorrow =:= true
            -> add_offset_datetime(DateTimeLocal, 24);
        true
            -> DateTimeLocal
        end,

    % For each hour in hours, we build local datetime
    % convert it back to UTC and offset by ?BEMS_UTC_OFFSET_HOURS
    HoursDateTimesBEMS = 
        [ 
            convert_utc_to_offset(
                calendar:local_time_to_universal_time(
                    {{CurrentYear, CurrentMonth, CurrentDay}, {Hour, 0, 0}}
                ), 
                ?BEMS_UTC_OFFSET_HOURS
            ) || Hour <- Hours ],
    ?LOGDEBUG("HoursDateTimesBEMS: ~p", [HoursDateTimesBEMS]),

    % Form a list of maps with date string and corresponding hours
    % At most 2 different dates will be present because we 
    % at most request full 24 hours locally, and it could span 2 dates in BEMS timezone
    DatesHoursList = 
        lists:foldl(
            fun(DateTime, Acc) ->
                {Date, {Hour, _, _}} = DateTime,
                DateStr = format_utc_date(DateTime),
                case lists:keyfind(DateStr, 1, Acc) of
                    {DateStr, HoursList} ->
                        % Date already present, append hour
                        NewHoursList = lists:append(HoursList, [Hour]),
                        lists:keyreplace(DateStr, 1, Acc, {DateStr, NewHoursList});
                    false ->
                        % New date, add new entry
                        [{DateStr, [Hour]} | Acc]
                end
            end, [], HoursDateTimesBEMS),
    ?LOGDEBUG("DatesHoursList: ~p", [DatesHoursList]),

    % For each date, make a separate request
    % request_data returns {ok, [Response]} or {error, Reason}, so we collect it 
    % as [ok, [Response]] or [ok, [Response1, Response2]], or as [error, [Reason]]
    ResultsRaw =
        lists:map(
            fun({Date, HoursList}) ->
                request_data_single(Token, Date, HoursList, Objects)
            end,
            DatesHoursList),

    % All ok => ok, any other => error
    Status = lists:foldl(
        fun
            ({ok, _}, ok) -> ok;
            (_, acc) -> error
        end, ok, ResultsRaw),
    ?LOGDEBUG("Status: ~p", [Status]),

    % Collect list of reasons in case of error
    Reasons = lists:foldl(
        fun
            ({error, Reason}, Acc) -> [Reason | Acc];
            (_, Acc) -> Acc
        end, [], ResultsRaw),
    
    % The each second term is a list of a single element, we turn it into a flat list
    Results =
        case Status of
            ok ->
                lists:foldl(
                    fun({ok, [Response]}, Acc) -> [Response | Acc];
                        (_, Acc) -> Acc
                    end, [], ResultsRaw);
            error ->
                Reasons
        end,
    ?LOGDEBUG("Results: ~p", [Results]),

    {Status, Results}.

request_data_single(Token, Date, Hours, Objects) ->
    Url = <<"https://bems.kegoc.kz/integration/api/v1/integration/plans">>,

    %% Формируем тело запроса
    Body = #{<<"date">> => Date, <<"hours">> => Hours, <<"objects">> => Objects},
    ?LOGDEBUG("Body ~p",[Body]),
    RequestBody = jsx:encode(Body),

    %% Формируем заголовки
    HTTPHeaders = [
        {"Authorization", <<"Bearer ", Token/binary>>},
        {"Content-Type", "application/json"}
    ],

    %% Формируем HTTP-запрос
    HTTPRequest = {Url, HTTPHeaders, "application/json", RequestBody},
    ?LOGDEBUG("Plans HTTP Request: ~p", [HTTPRequest]),

    %% Опции запроса
    Options = [], %% Тайм-аут 10 секунд

    %% Выполняем запрос
    case httpc:request(post, HTTPRequest, [], Options) of
        %% Успешный ответ
        {ok, {{_, 200, _}, _Headers, ResponseBody}} ->
            BinaryBody = case is_binary(ResponseBody) of
                true -> ResponseBody;
                false -> list_to_binary(ResponseBody)
            end,
            % ?LOGDEBUG("ResponseBody as a binary: ~p", [BinaryBody]),
            {ok, jsx:decode(BinaryBody, [return_maps])};
        {ok, {{_, Code, _}, _Headers, ResponseBody}} ->
            B = list_to_binary(ResponseBody),
            R = jsx:decode(B, [return_maps]),
            ?LOGERROR("Unexpected status code: ~p, Response: ~p", [Code, R]),
            {error, {unexpected_status, Code}};
        {error, Reason} ->
            ?LOGERROR("Connection error: ~p", [Reason]),
            {error, Reason}
    end.

process_data(OIDs, Objects, Response) ->
    case Response of
        #{<<"date">> := Date, <<"objects">> := ObjectsList} ->
            % ?LOGDEBUG("Date: ~p, ObjectsList: ~p", [Date,ObjectsList]),
            
            TransformData = lists:map(fun(Obj) ->
                % ?LOGDEBUG("transform_object: ~p",[Obj]),
                Code = maps:get(<<"code">>, Obj),
                Purchases = transform_data(maps:get(<<"purchases">>, Obj, []), Date),
                Sales = transform_data(maps:get(<<"sales">>, Obj, []), Date),
                #{code => Code, purchases => Purchases, sales => Sales}
            end, ObjectsList),
        
            % ?LOGDEBUG("DEBUG TransformData,OIDs, Objects: ~p, ~p, ~p", [TransformData,OIDs, Objects]),
            
            case find_matching_maps_with_codes(TransformData, OIDs, Objects) of
                Data ->
                    lists:foreach(
                        fun({ #{ code := Code, purchases := TransformedPurchases, sales := TransformedSales }, OID }) ->
                            Path = fp_db:to_path(OID),
                            Points = [<<Path/binary, "/purchase">>, 
                                     <<Path/binary, "/sale">>],
                            DataList = [TransformedPurchases, TransformedSales],
                            % ?LOGDEBUG("DataList ~p ",[DataList]),
                            lists:foreach(
                                fun({Point, Item}) ->
                                    case write_to_db(Point, Item) of
                                        {ok,_} -> ok;
                                        {ignore,_}->
                                            % ?LOGDEBUG("No data for archive: ~p", [Point]);
                                            ok;
                                        {error, Reason0} ->
                                            ?LOGERROR("Failed to write to archive ~p: ~p", [Point, Reason0]);
                                        _->
                                            ?LOGWARNING("Unexpected response: ~p", [Point])
                                    end
                                end, lists:zip(Points, DataList) )
                        end, Data 
                    );
                _ ->
                    ?LOGERROR("No matching data found in Response: ~p", [Response]),
                    {error, no_match}
            end;
        _ ->
            ?LOGERROR("Invalid Response format: ~p", [Response]),
            {error, invalid_response}
    end.
    
write_to_db(Point, Data) ->
    % ?LOGDEBUG("write Point ~p", [Point]),
    % ?LOGDEBUG("write Data ~p", [Data]),
    % Extract boundaries of the data to delete the old data before insertion
    Archive = <<Point/binary,"/archives/out_value">>,
    % ?LOGDEBUG("Archive ~p",[Archive]),
    case Data of
        [] -> 
            {ignore, none};
        Data ->
            Head = hd(Data),
            Last = lists:last(Data),
            {From, _} = Head,
            {To, _} = Last,
            % ?LOGDEBUG("From ~p,To ~p",[From,To]),
            % ?LOGDEBUG("Data ~p",[Data]),
            % Delete the existing data points in the given range
            fp_ts:delete_period(project_ts_database, [Archive], From, To),
            % ?LOGDEBUG("Data deleted From ~p, To ~p",[From,To]),
            % Insert new data points into the archive
            fp_archive:insert_values(Archive, Data),
            {ok, none}
        
    end.
        
% Определите функцию для поиска
find_matching_maps_with_codes(Maps,OIDs,Objects) ->
    O = lists:zip(OIDs,Objects),
    [ 
        {Map, OID} || {OID, Code} <- O,
        Map <- Maps,
        maps:get(code, Map) =:= Code
    ].

int_to_binary_string(Int) when is_integer(Int) ->
    %% Format integer as a string
    Str = io_lib:format("~p", [Int]),
    %% Convert list of characters to binary
    list_to_binary(Str).
    
format_utc_time() ->
    {{Year, Month, Day}, {Hour, Minute, Second}} = calendar:universal_time(),
    FormattedYear = Year rem 100, % Get last two digits of the year
    io_lib:format("~2..0B/~2..0B/~2..0B ~2..0B:~2..0B:~2..0B",[FormattedYear, Month, Day, Hour, Minute, Second]).
                  
format_utc_date(DateTime) ->
    {{Year, Month, Day}, _} = DateTime,
    list_to_binary(io_lib:format("~4..0B-~2..0B-~2..0B", [Year, Month, Day])).

transform_data(Items, Date) ->
    lists:map(fun(Item) ->
        Hour = maps:get(<<"hour">>, Item, 0),
        Value = maps:get(<<"value">>, Item),
        Ts = calculate_timestamp(Date, Hour),
        {Ts, Value}
    end, Items).

% Функция для вычисления временной метки, данные приходитят со смещение +4, что требует преобразования в UTC
calculate_timestamp(Date, Hour) ->
    try
        {Year, Month, Day} = date_binary_to_date(Date),
        % Construct DateTime
        DateTime = convert_offset_to_utc({{Year, Month, Day}, {Hour, 0, 0}}, ?BEMS_UTC_OFFSET_HOURS),
        datetime_to_unix(DateTime) * 1000
    catch
        _:Error ->
            ?LOGERROR("Failed to calculate timestamp for Date ~p, Hour ~p: ~p", [Date, Hour, Error]),
            {error, invalid_input}
    end.
    
% Function to convert date-time to Unix time
datetime_to_unix({Date, Time}) ->
    % Calculate seconds from Gregorian epoch (0 AD)
    GregorianSeconds = calendar:datetime_to_gregorian_seconds({Date, Time}),
    % ?LOGDEBUG("DEBUG Date upto now in GregorianSeconds, sec: ~p", [GregorianSeconds]),
    % Gregorian seconds for Unix epoch start
    UnixEpochSeconds = calendar:datetime_to_gregorian_seconds({{1970, 1, 1}, {0, 0, 0}}),
    % ?LOGDEBUG("DEBUG Date upto UnixEpochSeconds in GregorianSeconds, sec: ~p", [UnixEpochSeconds]),
    % Subtract to get Unix time
    UnixTime = GregorianSeconds - UnixEpochSeconds,
    UnixTime.

date_binary_to_date(BinaryDate) ->
    %% Assume input is "YY/MM/DD"
    case binary:split(BinaryDate, <<"-">>, [global]) of
        [YearBin, MonthBin, DayBin] ->
            { binary_to_integer(YearBin), binary_to_integer(MonthBin), binary_to_integer(DayBin) };
        _ ->
            {error, invalid_format}
    end.

update_value(Point)->
    % ?LOGDEBUG("Point: ~p", [Point]),
    Archive = <<Point/binary,"/archives/out_value">>,
    {Date,{Hour,_,_}} = calendar:universal_time(),
    Ts = datetime_to_unix({Date,{Hour,0,0}}) * 1000,
    try
        {T, V} = fp_archive:get_point(Archive,Ts),
        [Ts,Value] = if is_number(V)-> [T,V]; true -> [T, -1] end,
        fp_db:edit_object(?OBJECT(Point), #{<<"in_value">>=>Value,<<"in_ts">>=>Ts}),
        {ok,none}
    catch
        ClE:Error ->
            ?LOGERROR("Error: ~p", [Error]),
            {error, {read_failure, Error}}
    end.

%% Функция для преобразования даты/времени из часового пояса со смещением
%% OffsetHours — это целое число (например, 5 для UTC+5, или -3 для UTC-3)
convert_offset_to_utc(DateTime, OffsetHours) ->
    add_offset_datetime(DateTime, -OffsetHours).

%% Функция для преобразования даты/времени в часовой пояс со смещением
%% OffsetHours — это целое число (например, 5 для UTC+5, или -3 для UTC-3)
convert_utc_to_offset(DateTime, OffsetHours) ->
    add_offset_datetime(DateTime, OffsetHours).
    
add_offset_datetime(DateTime, OffsetHours) ->
    % 1. Преобразуем смещение (часы) в секунды
    OffsetSecs = OffsetHours * 3600,
    
    % 2. Преобразуем локальное время в общее число секунд (Григорианские секунды)
    LocalSecs = calendar:datetime_to_gregorian_seconds(DateTime),
    
    % 3. Вычитаем смещение, чтобы получить время в UTC
    % Примечание: Для перевода ИЗ локального времени В UTC, смещение ВСЕГДА ВЫЧИТАЕТСЯ.
    UtcSecs = LocalSecs + OffsetSecs,
    
    % 4. Преобразуем секунды UTC обратно в формат {Date, Time}
    UtcDateTime = calendar:gregorian_seconds_to_datetime(UtcSecs),
    
    UtcDateTime.
    
find_items()->
    % get .oid, .name, id from * where and( .pattern=$oid('/root/FP/prototypes/subject/fields'), disabled=false)
    % ?LOGDEBUG("find_objects/3: Root: ~p, Name: ~p, Pattern: ~p", [Root,Name,Pattern]),
    Query = {'AND', [ {<<"id">>, ':<>', none},
                {<<".pattern">>, '=', fp_db:to_oid(<<"/root/FP/prototypes/subject/fields">>)},
                {<<"disabled">>, ':=', false} ]},
    Objects =
        try
            fp_db:get( [?PROJECT_DB], [<<".oid">>, <<"id">>], Query )
        catch
            E:R:C -> 
                ?LOGERROR( "Error: ~p ~p ~p",[E,R,C]),
                {error,[[], []]}
        end,
    % ?LOGDEBUG("find_objects/3: ~p", [Objects]),
    {ok,Objects}.