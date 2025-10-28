function(VARS,element,context){
    
    const screen = fp.rt.get_screen();
    
    function Dateplace(values, timestamps) {
        if (timestamps.length === 0) {
            return [];
        }
    
        if (values.length === 0 || timestamps[timestamps.length - 1] < values[0][0]) {
            return new Array(timestamps.length).fill(["", ""]);
        }
    
        const result = [];
        let valueIndex = 0;
    
        for (let ts of timestamps) {
            while (values[valueIndex][0] < ts) {
                if (valueIndex === values.length - 1) {
                    return result.concat(
                        new Array(timestamps.length - result.length).fill(["", ""])
                    );
                }
                valueIndex++;
            }
    
            let r;
    
            if (valueIndex === 0 && values[valueIndex][0] !== ts) {
                r = "";
            } else if (values[valueIndex][0] === ts) {
                r = values[valueIndex][1];
            } else {
                r = values[valueIndex - 1][1];
            }
    
            result.push([ts, r]); // <<<< теперь добавляем пару
        }
    
        return result;
    }

    
    context._button_filter=true;
    const fields = [
        ".name", 
        ".pattern", 
        ".folder", 
        ".fp_path",
        "title",
        "input_range",
        "model_input",
        "model_path",
        "output_range",
        "step",
        "model_port",
        "model_host",
        "workers"
    ].join(", ");
    
    let object_type = 'models';
    
    let baseFilter = `and(.pattern=$oid('/root/FP/catalogs/${object_type}/fields'))`;
    const query = `get ${fields} from * where ${baseFilter} format $to_json`;
    const connection = context.get_connection();

    
    const step_ms = 3600000;
    const n_values = 24; 
    let from = +new Date();
    from = Math.floor(from / (3600000 * 24)) * 3600000 * 24 - 3600000 * 4;
    const to = from + step_ms * n_values;
    const timestamps = Array.from({ length: n_values }, (_, i) => from + i * step_ms);
    
    connection.get(query, data => {
        
        // Filter
        data = data.filter(d => d[".fp_path"] !== undefined && d["step"] === 3600)
        
        // Make data for both ground truth and forecast
        const n_entries = data.length;
        let data_orig = data;
        data = [];
        for (let i = 0; i < n_entries; i++) {
            data.push(structuredClone(data_orig[i]));
            data.push(structuredClone(data_orig[i]));
            data.push(structuredClone(data_orig[i]));
        }
        // console.log(data);
        
        // Fill archive values
        for (let i = 0; i < n_entries; i++){
            // Set titles
            data[3 * i + 0]["title"] = data_orig[i]["title"] + " (факт)";
            data[3 * i + 1]["title"] = data_orig[i]["title"] + " (прогноз)";
            data[3 * i + 2]["title"] = data_orig[i]["title"] + " (|отклонения|, %)";

            // Forecast
            let archive_gt = "";
            if (data_orig[i]["model_input"] !== null && data_orig[i]["model_input"].length > 0) {
                archive_gt = data_orig[i]["model_input"][0];
            }
            let archive_forecast = "";
            if (data_orig[i]["workers"] !== null && data_orig[i]["workers"].length > 0) {
                archive_forecast = data_orig[i]["workers"][0] + "/archives/out_value";
            }

            connection.application(
                "fp_json",
                "read_archives",
                {
                    archives: [
                        archive_gt,
                        archive_forecast
                    ],
                    from,
                    to
                },
               response => {
                    let values_gt = response[archive_gt] || [];
                    let values_forecast = response[archive_forecast] || [];
                    
                    // Заменяем null на ""
                    values_gt = values_gt.map(([ts, value]) => [ts, value === null ? "" : value]);
                    values_forecast = values_forecast.map(([ts, value]) => [ts, value === null ? "" : value]);
                    
                    // Приводим к одному ряду с timestamps
                    values_gt = Dateplace(values_gt, timestamps);
                    values_forecast = Dateplace(values_forecast, timestamps);
                
                    // GT & forecast from the archives
                    for (let j = 0; j < 2; j++) {
                        let sum = 0.0;
                        let count = 0;
                        let index = (j === 0) ? 3 * i + 0 : 3 * i + 1;
                        let values = (j === 0) ? values_gt : values_forecast;
                        
                        if (values.length !== 0) {
                            for (let k = 0; k < n_values; k++) {
                                let [ts, val] = values[k];  // берём сразу ts и val
                                if (val !== "") {
                                    data[index]["value_" + k] = [ts, val]; // кладём массив
                                    sum += val;
                                    count += 1;
                                } else {
                                    data[index]["value_" + k] = [ts, ""]; // пустое значение, но с ts
                                }
                            }
                            if (count > 0) {
                                data[index]["mean"] = (sum / count).toFixed(1);
                            } else {
                                data[index]["mean"] = "";
                            }
                        }
                    }
                
                    // Deviation
                    let sum = 0.0;
                    let count = 0;
                    for (let k = 0; k < n_values; k++) {
                        let [ts_gt, val_gt] = values_gt[k];
                        let [ts_forecast, val_forecast] = values_forecast[k];
                
                        if (val_gt !== "" && val_forecast !== "") {
                            if (Math.abs(val_gt) > 0) {
                                let val = (
                                    Math.abs(val_gt - val_forecast) / Math.abs(val_gt) * 100.0
                                );
                                data[3 * i + 2]["value_" + k] = [ts_gt, val]; // кладём [ts, deviation]
                
                                sum += val;
                                count += 1;
                            } else {
                                data[3 * i + 2]["value_" + k] = [ts_gt, ""];
                            }
                        } else {
                            data[3 * i + 2]["value_" + k] = [ts_gt, ""];
                        }
                    }
                    if (count > 0) {
                        data[3 * i + 2]["mean"] = (sum / count).toFixed(1);
                    } else {
                        data[3 * i + 2]["mean"] = "";
                    }
                    
                    const [Footer] = screen.find_by_name("footer");
                    const From = fp_dev.datetimeToString(timestamps[0])
                    const To = fp_dev.datetimeToString(timestamps[timestamps.length - 1])
                    // console.log(From,Footer);
                    const FooterText = `Данные выгружены с ${From} по ${To}` 
                    Footer.set({text : FooterText})
                    
                    element.set({ data });
                },
                error => {
                    console.error( data_orig[i], error );
                }
            );
        }
    }, console.error);
}
