import http from 'node:http';
import worker from '../dist/server/index.js';
const port=Number(process.env.PORT||8787);
http.createServer(async(req,res)=>{
  try {
    const request=new Request(`http://127.0.0.1:${port}${req.url}`,{method:req.method,headers:req.headers,...(['GET','HEAD'].includes(req.method)?{}:{body:req,duplex:'half'})});
    const response=await worker.fetch(request,{},{});
    res.writeHead(response.status,Object.fromEntries(response.headers));
    res.end(Buffer.from(await response.arrayBuffer()));
  } catch {res.writeHead(500,{'Content-Type':'text/plain'});res.end('Preview request failed');}
}).listen(port,'127.0.0.1',()=>console.log(`CardioResearch hosted preview: http://127.0.0.1:${port}`));
