function(VARS,element,context){
    
    const path = window.__worker;
    
    if(path !== null && path !== undefined && path.length > 0){
        const pattern = '/root/FP/prototypes/model_control/fields';
        const query = `GET task_status, task_message, task_updated, title from * WHERE AND(.path = '${path}', .pattern = $oid('${pattern}') )`;
        
        context.get_connection().find(query, (result) => {
                if(result.set.length >= 1){
                    context.__status.set({value : result.set[0].fields.task_status});
                    context.__message.set({value : result.set[0].fields.task_message});
                    context.__updated.set({value : result.set[0].fields.task_updated});
                    context.__model_name.set({value : result.set[0].fields.title});
                }
                
            },(e) => {
                console.log(`Set settings data error:`, e);
        },5000);
    }
    
    
}