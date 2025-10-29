function(VARS,element,context){
    const path = window.__worker;
    const conn = fp_dev.getConnection();
    
	if(path && path.length > 0){
        const pattern = '/root/FP/prototypes/model_control/fields';
        
        const query = `GET run_task from * WHERE AND(.path = '${path}', .pattern = $oid('${pattern}') )`;
        
        conn.find(query, (result) => {
                if(result.set.length >= 1){
                    let value = result.set[0].fields.run_task;
                    value = Number.isInteger(value) ? value + 1 : 0;
                	if (value > 10) {
                	    value = 0;
                	};
                	
                	conn.edit_object(path, {run_task: value},  () => {console.log("excute data success")}, () => {console.log("excute data error")})
                }
            },(e) => {
                console.log(`Set settings data error:`, e);
        },5000);
    }
}