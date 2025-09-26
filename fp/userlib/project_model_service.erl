
%%-----------------------------------------------------------------
%% This script is executed at the server side. The programming language
%% is Erlang.
%% All this methods accept an Object of the instance and can edit or perform any other allowed code.
%% If any of the methods throw or crash the whole transaction will rollback.
%% If there are any warnings or not critical errors it is recommended to log them with available macros, examples:
%%  ?LOGINFO( "my info text: ~p", [Info] )
%%  ?LOGWARNING( "my warning text: ~p", [Warning] )
%%  ?LOGERROR( "my error text: ~p", [Error] )
%% If the methods performs well it should return atom 'ok'.
%% For more info please refer to the documentation
%%-----------------------------------------------------------------

-module(project_model_service).
-import(string,[concat/2]).
%%---------------------------------------

-include("fp.hrl").

-export([
    run_task/1,
    call/2,
    write_to_db/2
  ]).
    
run_task(Obj)->
    ObjPath = fp_db:to_path(Obj),
    ModelOutput = ?OID(<<ObjPath/binary, "/archives/out_value">>),
    
    ?LOGINFO("model_service: Run the task..."),
    ?LOGINFO("model_service: at path: ~p", [ObjPath]),

    {ok, ModelNameID} = fp_db:read_field(Obj, <<"model_name">>),
    ?LOGINFO("model_service: ModelNameID: ~p", [ModelNameID]),
    CatalogObject = try
        ?OBJECT(ModelNameID)
    catch
      E0:R0:C0 -> 
        ?LOGINFO("model_service: ~p ~p ~p",[E0,R0,C0])
    end,
    
    #{
        <<"input_range">> := InputRange, 
        <<"output_range">> := OutputRange, 
        <<"model_path">> := ModelPath,
        <<"step">> := Step,
        <<"model_input">> := ModelInput, 
        <<"model_port">> := Port, 
        <<"model_host">> := Host
    } = try
        fp_db:read_fields( CatalogObject, [<<"input_range">>, <<"output_range">>, <<"model_path">>, <<"step">>, <<"model_input">>, <<"model_port">>, <<"model_host">>, <<"model_output">>] )
    catch
      E1:R1:C1 -> 
        ?LOGINFO("model_service: ~p ~p ~p",[E1,R1,C1])
    end,
    
    ?LOGINFO("~p ~p ~p ~p ~p ~p ~p ~p", [ModelPath, InputRange, OutputRange, Step, ModelInput, Host, Port, ModelOutput]),
    
    run_task(Obj, ModelPath, InputRange, OutputRange, Step*1000, ModelInput, Host, Port, ModelOutput),
    
    #{}.
    
    
run_task(Obj, ModelPath, InputRange, OutputRange, Step, ModelInput, Host, Port, ModelOutput) ->
    try
        Dataset = [ read_from_db(InputRange, Step, A) || A<-ModelInput ],
        case request_body(ModelPath, InputRange, Step, Dataset) of
               {ok, Req} ->
                    Url = get_url(Host, Port),
                    case call(Url, Req) of
                        {ok, Response} ->
                            {<<"task_output">>, TaskOutput} = lists:keyfind(<<"task_output">>, 1, Response),
                            {<<"task_message">>, TaskMessage} = lists:keyfind(<<"task_message">>, 1, Response),
                            case transform(TaskOutput) of
                                 {ok, Data} ->         
                                    ?LOGINFO("Data after transformation: ~p", [Data] ),
                                    case write_to_db(Data, ModelOutput) of
                                        {ok,[DataAsBinString,From,To]}->
                                            ?LOGINFO( "Write to DB success" ),
                                            fp_db:edit_object(Obj, #{
                                                <<"task_status">>=><<"SUCCESS">>,
                                                <<"task_message">>=>TaskMessage,
                                                <<"task_updated">>=>list_to_binary(utc_time()),
                                                <<"task_from">>=>From,
                                                <<"task_to">>=>To,
                                                <<"output_data">>=>DataAsBinString
                                            }),
                                            
                                            ?LOGINFO( "Edit object success" );
                                        {error,_}->
                                            ?LOGERROR( "Write to DB failed", [])
                                    end;
                                 {error, TranformError} -> 
                                    ?LOGERROR( "Tranformation failed: ~p", [TranformError] )
                              end;
                        _-> ?LOGERROR( "Call failed", [] )
                    end;
                _->
                    ?LOGERROR("Bad request", [])
                    % throw({stop, none})
            end
    catch
      E:Rs:C -> 
        ?LOGINFO("model_service: ~p ~p ~p",[E,Rs,C])
    end,
    
    ?LOGINFO("model_service: success").
    

read_from_db(InputWindow, Step, Archive)->
    try
        % To = timestamp(),            % ms
        Current = (timestamp() div 3600000) * 3600000,            % ms
        To = Current + InputWindow * Step,            % ms
        From = Current - InputWindow * Step, 
        ?LOGINFO("model_service: From: ~p, To: ~p Step: ~p~n", [From, To, Step]),
        L = lists:seq(1, 2 * InputWindow),
        Ts0 = lists:map(fun(N) -> From + N * Step end, L),

        ?LOGDEBUG("model_service: Archive: ~p~n",[fp_db:to_path(Archive)]),
        ?LOGDEBUG("model_service: Timestamps: ~p~n",[Ts0]),

        Points = [fp_archive:get_point(Archive,Ts1) || Ts1 <- Ts0 ],
        
        ?LOGDEBUG("model_service: Points: ~p~n", [Points]),
        
        Data = [ if is_number(V)-> [K,V]; true -> [K, null] end || {K, V} <- Points ],
        Data
    catch
        ClE:Error ->
            ?LOGERROR("ClE: ~p, Error: ~p", [ClE,Error]),
            {error, {read_failure, Error}}
    end.


call(Url, DataMap) ->
    ?LOGINFO("URL, DataMap: ~p, ~p",[Url, DataMap]),
    try
        RequestJson = jsx:encode([DataMap]),
        
        % Set up HTTP request
        HTTPMethod  = post,
        HTTPHeaders = [{"Content-Type", "application/json"}],
        HTTPRequest = {Url, HTTPHeaders, "application/json", RequestJson},
        HTTPOptions = [],
        Options     = [{body_format, binary}],
        
        % Send the HTTP request
        case httpc:request(HTTPMethod, HTTPRequest, HTTPOptions, Options) of
            {ok, {{_, Code, _}, _, ResponseBody}} when Code >= 200, Code =< 299 ->
                Response = jsx:decode(ResponseBody),
                ?LOGINFO("Response ~p",[Response]),
                {ok, Response};  % Successful response

            {ok, {{_, Code, _}, _, _}} ->
                ?LOGERROR("model_service: Unexpected response code: ~p", [Code]),
                {error, {unexpected_response_code, Code}};
                
            {error, Error} ->
                ?LOGERROR("model_service: HTTP request error: ~p", [Error]),
                {error, {http_error, Error}}
        end
        
    catch
        _:HTTPError ->
            ?LOGERROR("HTTP Error: ~p",[HTTPError]),
            {error, http_request_failed}
    end.
  
% Function to safely get value or default if not found
get_value(Key, Default, List) ->
    case lists:keyfind(Key, 1, List) of
        false -> Default;
        {Key, Value} -> Value
    end.

int_to_binary_string(Int) when is_integer(Int) ->
    %% Format integer as a string
    Str = io_lib:format("~p", [Int]),
    %% Convert list of characters to binary
    list_to_binary(Str).
    
timestamp() ->
    erlang:system_time() div 1000000.

utc_time() ->
    {{Year, Month, Day}, {Hour, Minute, Second}} = calendar:universal_time(),
    FormattedYear = Year rem 100, % Get last two digits of the year
    io_lib:format("~2..0B/~2..0B/~2..0B ~2..0B:~2..0B:~2..0B",
                  [FormattedYear, Month, Day, Hour, Minute, Second]).

get_url(Host, Port) ->
    <<"http://", Host/binary, ":", Port/binary, "/predict/">>.

message(#{<<"task_message">>:=Message}) ->

    case Message of
        <<>> -> <<"No message">>;
        _ -> Message
    end.

write_to_db(Data, Archive) ->
    try
        % Extract boundaries of the data to delete the old data before insertion
        Head = hd(Data),
        Last = lists:last(Data),
        {From, _} = Head,
        {To, _} = Last,
        ?LOGINFO("From: ~p, To: ~p", [From, To]),
        ?LOGINFO("Archive: ~p", [Archive]),
        % Get the archive path
        Archive0 = fp_db:to_path(Archive),
        ?LOGINFO("Archive0: ~p", [Archive0]),
        
        ArchiveOID = ?OID( Archive ),
        DBName = fp_archive:get_storage(ArchiveOID),
        ?LOGINFO("DBName: ~p", [DBName]),
        ?LOGINFO("ArchiveOID: ~p", [ArchiveOID]),
        
        % Delete the existing data points in the given range
        % TODO: should we provide DBName instead of project_ts_database?
        fp_ts:delete_period(project_ts_database, [ArchiveOID], From, To),
        
        % Insert new data points into the archive
        Result = fp_archive:insert_values(Archive, Data),
        % ?LOGINFO("DEBUG: Result: ~p", [Result]),
        
        % Log success and return {ok}
        % ?LOGINFO("DEBUG: Data successfully written to archive: ~p", [Archive0]),
        
        % log to output_data field
        % String = io_lib:format("~p", [Data]),
        % ?LOGINFO("String: ~p", [String]),
        % DataAsBinString = list_to_binary(String),
        DataAsBinString = term_to_binary(Data),
        ?LOGINFO("Data: ~p", [Data] ),
        ?LOGINFO("Data as bin string: ~p", [DataAsBinString] ),
        ?LOGINFO("Data parsed back: ~p", [binary_to_term(DataAsBinString)] ),

        {ok, [DataAsBinString,From,To]}
        
    catch
        ClE:Error ->
            ?LOGERROR("Error: ~p, ClE: ~p", [ClE, Error]),
            {error, none}
    end.


transform(Data) ->
    % Handle undefined or empty results
    case Data of
        Data ->
            % Transform the result into tuples
            TData = [ {convert_timestamp_to_ms(Ts), D} || [Ts, D] <- Data ],
            % Return successful transformation
            {ok, TData};
        _ -> 
            {error, undefined_result}
    end.

    
request_body(ModelPath, OutputWindow, Step, Dataset) ->
    TaskId = int_to_binary_string(erlang:system_time()),  % Assuming TaskId is based on timestamp
    try
        % Construct the request body
        RequestBody = [
            { <<"task_id">>, TaskId},
            { <<"period">>, OutputWindow},
            { <<"step">>, Step},
            { <<"task_input">>, Dataset},
            { <<"model_path">>, ModelPath}
        ],
        % Return the request body as {ok, Body}
        {ok, RequestBody}
    catch
        % Handle unexpected errors
        _:Error ->
            ?LOGERROR("Error: ~p",[Error]),
            {error, failed_to_construct_body, none}
    end.
    
% Конвертация timestamp (в микросекундах или наносекундах) в миллисекунды
convert_timestamp_to_ms(Timestamp) when Timestamp < 1_000_000_000_000_000 ->
    % Предполагаем, что это миллисекунды
    Timestamp;

convert_timestamp_to_ms(Timestamp) when Timestamp < 1_000_000_000_000_000_000 ->
    % Предполагаем, что это микросекунды
    Timestamp div 1_000;

convert_timestamp_to_ms(Timestamp) when Timestamp < 1_000_000_000_000_000_000_000 ->
    % Предполагаем, что это наносекунды
    Timestamp div 1_000_000.