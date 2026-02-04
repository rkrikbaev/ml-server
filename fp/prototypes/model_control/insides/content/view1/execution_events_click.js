function(VARS,element,context){
    const path = window.__worker;
    const conn = fp_dev.getConnection();
    
	if(path && path.length > 0){
        const httpConnPath = path + "/http_client_connection";
        conn.edit_object(httpConnPath, {trigger: true},  () => {console.log("excute data success")}, () => {console.log("excute data error")})
    }
}