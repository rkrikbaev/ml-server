async function(VARS,element,context){
  window.__dialog_screen = element;
  
  fp.rt.get_server_time((time) => {
    const pattern = '/root/FP/prototypes/model_control/fields';
    const path = window.__worker;
            
    let colorList = [
      "#c9252d",
      "#12805c",
      "#cb6f10",
      "#4d2380ff"
    ];
    console.log(path);

    if(path !== null && path !== undefined && path.length > 0){
      const query = `GET task_status, task_message, task_updated, title, input from * WHERE AND(.path = '${path}', .pattern = $oid('${pattern}') )`;
      let arr = [];
      
      context.get_connection().find(query, async (result) => {
          // Set status fields
          if(result.set.length >= 1){
              context.__status.set({value : result.set[0].fields.task_status});
              context.__message.set({value : result.set[0].fields.task_message});
            //   context.__updated.set({value : result.set[0].fields.task_updated});
              context.__model_name.set({value : result.set[0].fields.title});
          }

          // Init trend archives
          for(let i = 0; i < result.total; i++){
              if(result.set[i].fields.input){
                for(let j = 0; j < result.set[i].fields.input.length; j++) {
                      if(j === 0) {
                          arr.push(
                          {
                                "oid": result.set[i].fields.input[j],
                                "caption": result.set[i].fields.input[j].replace("/root/FP/PROJECT", ""),
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
                                "oid": result.set[i].fields.input[j],
                                "caption": result.set[i].fields.input[j].replace("/root/FP/PROJECT", ""),
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
                                "oid": result.set[i].fields.input[j],
                                "caption": result.set[i].fields.input[j].replace("/root/FP/PROJECT", ""),
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
          }
          arr.push(
              {
                "oid": path + "/archives/out_value",
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
          context.__trend_element.pause();
          const oneDay = 24*60*60*1000;
          const from = Math.floor((time - 7 * oneDay) / oneDay) * oneDay - 5 * 60 * 60 * 1000;
          const to = from + 9 * oneDay;
          // console.log(from, to);
          
          context.__trend_element.set({archives:arr});
          
          const values = await context.__trend_element.load_from_to({from, to});
          
          context.__trend_element.update_dygraph(values);
          context.__trend_element.init_description();
          context.__trend_element.period.set({value : {from,to}});
      },(e) => {
          console.log(`Set archive error:`, e);
      },5000);
    }
  })
}