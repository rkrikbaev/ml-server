async function(VARS,element,context){
    window.__dialog_screen = element;
    
    fp.rt.get_server_time((time) => {
        console.log("@models");
        const worker = window.__worker;
        const model_input = window.__model_input;
        console.log(worker);
                
        let colorList = [
            "#c9252d",
            "#12805c",
            "#cb6f10",
            "#6f38b1"
        ];
        // console.log(worker);
        if(worker && worker.length > 0){
            console.log("Load model inputs");
            let arr = [];
            
            if(model_input){
               for(let j = 0; j < model_input.length; j++) {
                    if(j === 0) {
                        arr.push(
                        {
                              "oid": model_input[j],
                              "caption": model_input[j].replace("/root/FP/PROJECT", ""),
                              "type": "archive",
                              "axis": "y",
                              "group": "Fact",
                              "color": "#000000",
                              "settings": {
                                "strokeWidth": 1,
                                "pointSize": 1,
                                "drawPoints": false,
                                "stepPlot": true,
                                "visibility": "on"
                              }
                            }
                         );
                    } else if (j === 1) {
                        arr.push(
                            {
                              "oid": model_input[j],
                              "caption": model_input[j].replace("/root/FP/PROJECT", ""),
                              "axis": "y2",
                              "type": "archive",
                              "group": "Fact",
                              "color": colorList[j],
                              "settings": {
                                "strokeWidth": 1,
                                "pointSize": 1,
                                "drawPoints": false,
                                "stepPlot": true,
                                "visibility": "on"
                              }
                            }
                         );
                    } else {
                        arr.push(
                            {
                              "oid": model_input[j],
                              "caption": model_input[j].replace("/root/FP/PROJECT", ""),
                              "axis": "y",
                              "type": "archive",
                              "group": "Fact",
                              "color": colorList[j],
                              "settings": {
                                "strokeWidth": 1,
                                "pointSize": 1,
                                "drawPoints": false,
                                "stepPlot": true,
                                "visibility": "on"
                              }
                            }
                         );
                    }
                }
            }
            arr.push(
                {
                  "oid": worker + "/archives/out_value",
                  "caption": "out_value",
                  "axis": "y",
                  "type": "archive",
                  "group": "Predict",
                  "color": "#0d66d0",
                  "settings": {
                    "strokeWidth": 1,
                    "pointSize": 1,
                    "drawPoints": false,
                    "stepPlot": true,
                    "visibility": "on"
                  }
                }
             );
            console.log("arr", arr);
            context.__trend_element.pause();
            const oneDay = 24*60*60*1000;
            const from = Math.floor((time - 7 * oneDay) / oneDay) * oneDay - 5 * 60 * 60 * 1000;
            const to = from + 9 * oneDay;
            // console.log(from, to);
            
            context.__trend_element.set({archives:arr});
            
            const values = context.__trend_element.load_from_to({from, to});
            
            console.log(values);
            context.__trend_element.update_dygraph(values);
            
            context.__trend_element.init_description();
            
            context.__trend_element.period.set({value : {from,to}});
        }
    })
}