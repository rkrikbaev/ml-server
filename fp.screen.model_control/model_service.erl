
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

-module(model_service).
%%---------------------------------------

-include("fp.hrl").

-export([
    run_task/2,
    get_data/4,
    call/2,
    utc_time/0,
    timestamp/0
  ]).
    
run_task(Path, TaskStatus)->

    fp:log(info, "model_service: Run the task..."),
    
    Ts = timestamp(),
    
    Obj = fp_db:open(Path),

    Fields = [
                <<"task_id">>,
                <<"model_state">>,
                % <<"model_target">>,
                <<"model_input">>,
                <<"model_type">>,
                <<"model_version">>,
                <<"model_name">>,
                <<"model_input_granularity">>,
                <<"model_input_range">>,
                <<"model_output_range">>,
                <<"model_host">>,
                <<"model_port">>,
                <<"model_output">>]
     
    R = try
            fp_db:read_fields( Obj, Fields)
        catch
          E0:R0:C0 -> 
            fp:log(info, "model_service: ~p ~p ~p",[E0,R0,C0])
        end,
                                                            
    #{
        <<"task_id">>:=TaskId,
        <<"model_state">>:=State,
        % <<"model_target">>:= Target,
        <<"model_input">>:= Archives,
        <<"model_type">>:= ModelType0,
        <<"model_version">>:= ModelVersion,
        <<"model_name">> := ModelName,
        <<"model_input_granularity">> := Step,
        <<"model_input_range">> := InputWindow0,
        <<"model_output_range">> := OutputWindow,
        <<"model_host">> := Host,
        <<"model_port">> := Port,
        <<"model_output">>:= OutputArchive} = R,

    % Set default values if any of the variables are 'none'
    OutputWindow1 = case OutputWindow of none; _ when not is_number(OutputWindow) -> 24; _ -> OutputWindow end,
    InputWindow1 = case InputWindow of none; _ when not is_number(InputWindow) -> 0; _ -> InputWindow end,
    Step1 = case Step of none; _ when not is_number(Step) -> 3600000; _ -> Step end,    

    fp:log(info, "model_service: read the object: ~p", [R]),
    
    case TaskStatus of
    
        1 ->
            try

                Dataset = [ read_from_db(InputWindow, Step, Ts, A) || A<-Archives ],
                % fp:log(debug, "model_service: Dataset: ~p~n", [Dataset]),
                
                Request = request_body(TaskStatus, OutputWindow1, InputWindow1, Step1, Dataset),           
                
                Url = get_url(Host, Port),

                fp_db:edit_object(Obj, #{
                            <<"task_status">>=>TaskStatus,
                            <<"task_updated">>=>list_to_binary(utc_time()),,
                            <<"task_id">>=>NewTaskId}), 
                
                case call(Url, Request) of
                
                    {ok, Response} ->

                        Data = case transform(Response) of
                            {ok, Result} -> Result;
                            {error, Error} -> throw({stop, Error})
                        end;

                        write_to_db(Data, OutputArchive),

                        NewMessage = message(Response),

                        #{<<"task_status">>:=Status} = Response,
                        fp_db:edit_object(Obj, #{
                                                    <<"task_status">>=>Status,
                                                    <<"task_updated">>=>list_to_binary(utc_time()),
                                                    <<"task_message">>=>NewMessage,
                                                    <<"model_state">>=><<"STDBY">>
                        }),
                        fp:log(info, "model_service: Task Updated: ~p~n", [TaskUpdated]);
                    
                    { error, Error }->
                        fp:log(info,"model_service: Error when call the model",[])
                end
            catch
              E:Rs:C -> 
                fp:log(info, "model_service: ~p ~p ~p",[E,Rs,C])
            end;
            
        2 ->
            [
                { <<"model_type">>, ModelType},
                { <<"model_version">>, ModelVersion},
                { <<"model_name">>, ModelName},
                { <<"model_object">>, Path}, 
                { <<"task_id">>, TaskId}
            ];
        _->
            fp:log(info, "model_service: No tasks~n",[])
            % throw({stop, no_tasks})
    end,
    
    ok.
    

read_from_db(InputWindow, Step, Ts, Archive)->
    try
        To = Ts,            % nsec
        From = To - InputWindow * 3600000, 
        fp:log(info, "model_service: From: ~p, To: ~p Step: ~p~n", [From, To, Step]),
        
        L = lists:seq(1, InputWindow),
        Ts0 = lists:map(fun(N) -> From + N * Step end, L),

        fp:log(info, "model_service: Archive: ~p~n",[fp_db:to_path(Archive)]),
        % fp:log(info, "model_service: Timestamps: ~p~n",[Ts0]),
        
        Points = [fp_archive:get_point(Archive,Ts1) || Ts1 <- Ts0 ]
        
        % fp:log(info, "model_service: Points: ~p~n", [Points]),
        
        Data = [ if
                    is_number(V)-> [K,V];
                    true -> [K, null]
                    end || {K, V} <- Points ]
                
        Archive0 = fp_db:to_path(Archive),
        % fp:log(info, "model_service: Data: ~p~n", [Data]),
        
        Dataset = [{Archive0, Data}]
    catch
        ClE:Error ->
            fp:log(error, "model_service: Failed to read from DB: ~p", [Error]),
            {error, {read_failure, Error}}
    end.


call(Url, DataMap) ->
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
                {ok, Response};  % Successful response

            {ok, {{_, Code, _}, _, _}} ->
                fp:log(error, "model_service: Unexpected response code: ~p", [Code]),
                {error, {unexpected_response_code, Code}};
                
            {error, Error} ->
                fp:log(error, "model_service: HTTP request error: ~p", [Error]),
                {error, {http_error, Error}}
        end
    catch
        _:HTTPError ->
            {error, http_request_failed}.
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
    erlang:system_time() div 1000.
ok.

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
        
        % Get the archive path
        Archive0 = fp_db:to_path(Archive),
        DBName = fp_archive:get_storage(Archive0),
        
        % Delete the existing data points in the given range
        fp_ts:delete_period(DBName, [Archive0], From, To),
        
        % Insert new data points into the archive
        fp_archive:insert_values(Archive0, Data),
        
        % Log success and return {ok}
        fp:log(debug, "model_service: Data successfully written to archive: ~p", [Archive0]),
        {ok, written_to_db}
    catch
        ClE:Error ->
            fp:log(error, "model_service: Failed to write to DB: ~p", [Error]),
            {error, {write_failure, Error}}
    end.


transform(#{<<"task_output">> := Result}) ->
    % Handle undefined or empty results
    case Result of
        undefined -> 
            {error, undefined_result};  % Return error for undefined result
        _ ->
            % Transform the result into tuples
            Data = [ {A, B} || [A, B] <- Result ],
            
            % Log the result
            fp:log(debug, "model_service: Result: ~p", [Data]),
            
            % Return successful transformation
            {ok, Data}
    end;

transform(_) ->
    {error, invalid_response_format}.  % Catch-all clause for unexpected input.

    
request_body(TaskStatus, OutputWindow, InputWindow, Step, Dataset) ->
    try
        TaskId = int_to_binary_string(erlang:system_time()),  % Assuming TaskId is based on timestamp
        
        % Construct the request body
        RequestBody = [
            { <<"task_id">>, TaskId},
            { <<"task_status">>, TaskStatus},
            { <<"model_output_range">>, OutputWindow},
            { <<"model_input_range">>, InputWindow},
            { <<"model_input_granularity">>, Step},
            { <<"task_input">>, Dataset}
        ],
        
        % Return the request body as {ok, Body}
        {ok, RequestBody}
    catch
        % Handle unexpected errors
        _:Error ->
            {error, failed_to_construct_body}.
    end.

