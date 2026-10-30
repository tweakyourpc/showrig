// Creates explicitly synthetic design studies through FigCraft's real command engine.
import net from 'node:net';
import {execFileSync} from 'node:child_process';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve,join} from 'node:path';
const out=resolve(process.argv[2]||'build/design');mkdirSync(out,{recursive:true});
const port=Number(execFileSync('portbroker',['get','--name','showrig-next-figcraft'],{encoding:'utf8'}).trim());
const socket=net.connect(port,'127.0.0.1');let buffer='',counter=0;const pending=new Map();
socket.setTimeout(60000,()=>socket.destroy(new Error('FigCraft timeout')));
socket.on('data',data=>{buffer+=data;while(buffer.includes('\n')){const at=buffer.indexOf('\n'),r=JSON.parse(buffer.slice(0,at));buffer=buffer.slice(at+1);const p=pending.get(r.id);pending.delete(r.id);if(r.ok)p.resolve(r.result);else p.reject(new Error(r.error));}});
socket.on('error',error=>{for(const p of pending.values())p.reject(error);});
const call=(method,params)=>new Promise((resolve,reject)=>{const id=++counter;pending.set(id,{resolve,reject});socket.write(JSON.stringify({id,method,params})+'\n');});
const commands=[],C={paper:'#F6F3EC',white:'#FFFEFA',ink:'#23332F',muted:'#58655F',green:'#18594D',pale:'#DCEBE3',violet:'#594787',amber:'#853E20'};
function cmd(command,params,as){commands.push({command,params,...(as?{as}:{})});}
let count=0;
function box(parent,x,y,width,height,fill,name='Surface'){const as=`node${++count}`;cmd('node.create',{type:'frame',name,x,y,width,height,select:false,props:{fill,cornerRadius:10},...(parent?{parent:{$ref:parent}}:{})},as);return as;}
function label(parent,x,y,text,size=16,color=C.ink,width=500,bold=false){const as=`node${++count}`;cmd('node.create',{type:'text',name:text.slice(0,70),parent:{$ref:parent},x,y,width,height:size*2.8,text,select:false,props:{fill:color,fontFamily:'DejaVu Sans',fontSize:size,fontStyle:bold?'Bold':'Book',textAutoResize:'height'}},as);return as;}
function button(parent,x,y,width,text,primary=false){const id=box(parent,x,y,width,46,primary?C.green:C.white,text);label(id,14,12,text,14,primary?C.white:C.ink,width-24,true);return id;}
cmd('file.new',{name:'Showrig Next · Creative workbench'});cmd('page.rename',{name:'Synthetic interface studies'});
const editor=box(null,0,0,1440,960,C.paper,'01 · Scene workspace');
box(editor,0,0,1440,80,C.white);label(editor,28,22,'showrig.',28,C.green,190,true);label(editor,260,20,'A story worth keeping',18,C.ink,480,true);label(editor,260,48,'Synthetic design example · your film, your source files',12,C.muted,650);button(editor,1170,18,240,'Film settings');
label(editor,28,104,'01  Scenes',15,C.green,200,true);const reviewLink=button(editor,230,91,230,'02  Review & export');label(editor,1100,104,'3 scenes · Landscape',14,C.muted,300);
box(editor,0,150,240,730,'#EEEEE5');label(editor,22,174,'STORY OUTLINE',12,C.muted,200,true);
['The idea','Show the process','An invitation'].forEach((name,i)=>{const card=box(editor,14,220+i*100,212,86,i===0?C.white:'#EEEEE5');label(card,14,14,`0${i+1}   ${name}`,14,C.ink,190,true);label(card,42,47,i===1?'! Needs content':'✓ Has content',13,i===1?C.amber:C.green,170);});button(editor,18,550,204,'＋ Add scene');
box(editor,242,150,620,730,C.white);label(editor,276,176,'SCENE 01 / OPENING',12,C.muted,400,true);label(editor,276,207,'Shape the scene.',32,C.ink,550);label(editor,276,258,'What should the viewer remember?',15,C.muted,540);
label(editor,276,308,'Heading',14,C.ink,500,true);box(editor,276,340,550,52,C.paper);label(editor,291,354,'A story worth keeping',16,C.ink,510);
label(editor,276,417,'On-screen text',14,C.ink,500,true);box(editor,276,450,550,90,C.paper);label(editor,291,465,'The finished film is only the beginning.',17,C.ink,500);
button(editor,276,566,300,'＋ Add pictures or video');button(editor,590,566,236,'Add backdrop');label(editor,276,643,'Narration & captions',17,C.ink,400,true);label(editor,276,680,'Text captions · no generated voice',14,C.muted,500);box(editor,276,718,550,98,C.paper);label(editor,291,734,'Your voice. Your pace. Your point of view.',16,C.muted,510);
label(editor,890,176,'SCENE LAYOUT · NO MOTION OR SOUND',12,C.muted,510,true);const canvas=box(editor,890,215,520,293,'#182B28');label(canvas,34,72,'A story worth\nkeeping.',34,C.white,450,true);box(canvas,36,184,66,4,'#A3CEB7');label(canvas,36,215,'The finished film is only the beginning.',15,'#D7E7DD',450);
label(editor,890,541,'Build the film. Keep the craft.',22,C.ink,510,true);label(editor,890,585,'Your scenes become an editable timeline.\nTitles, media and decisions stay yours.',16,C.muted,500);button(editor,890,680,250,'Render film preview');label(editor,890,760,'FilmCraft timeline + media\nMP4 for sharing · source files for evolving',15,C.muted,500);
box(editor,0,880,1440,80,C.white);label(editor,28,899,'Saved on this computer',13,C.green,500);label(editor,28,925,'Text is enough. Add media when it serves the story.',13,C.muted,700);button(editor,1020,897,170,'Review film');const next=button(editor,1200,897,210,'Next scene →',true);
const review=box(null,1500,0,1440,960,C.paper,'02 · Review and recovery');label(review,40,30,'showrig.',28,C.green,250,true);label(review,40,140,'Keep the film.\nKeep the craft.',48,C.ink,950);label(review,44,278,'Two artifacts. One creative work.',19,C.muted,800);
[['Video','MP4 · ready to share'],['Editable source','FilmCraft + media · ready to evolve']].forEach(([title,sub],i)=>{const card=box(review,40+i*680,350,650,160,C.white);label(card,28,26,title,26,C.ink,560,true);label(card,28,86,sub,17,C.muted,580);});
const issue=box(review,40,550,1330,130,'#FAE9DF');label(issue,26,22,'Scene 2 needs content',22,C.amber,800,true);label(issue,26,68,'Add words or media, or remove the scene. Your draft stays saved.',17,C.ink,950);const fix=button(issue,1080,42,220,'Fix scene 2 →');button(review,40,745,240,'Back to scenes');button(review,1080,860,290,'Check before export',true);
const mobile=box(null,3000,0,390,844,C.paper,'03 · Mobile scene workspace');label(mobile,20,20,'showrig.',25,C.green,160,true);button(mobile,214,12,156,'Film settings');label(mobile,20,88,'Scenes',15,C.green,150,true);label(mobile,180,88,'Review & export',15,C.muted,200);button(mobile,16,128,216,'01 / 03 · The idea');button(mobile,244,128,130,'Preview');label(mobile,20,202,'Shape the scene.',28,C.ink,350);label(mobile,20,256,'Heading',14,C.ink,350,true);box(mobile,20,284,350,52,C.white);label(mobile,32,298,'A story worth keeping',16,C.ink,330);label(mobile,20,364,'On-screen text',14,C.ink,350,true);box(mobile,20,393,350,110,C.white);label(mobile,34,410,'The finished film is only\nthe beginning.',17,C.ink,320);button(mobile,20,527,350,'＋ Add pictures or video');label(mobile,20,607,'Narration & captions',18,C.ink,350,true);label(mobile,20,650,'Text captions · no AI required',14,C.muted,350);box(mobile,0,744,390,100,C.white);label(mobile,20,753,'Saved on this computer',12,C.green,350);button(mobile,20,786,160,'Review film');button(mobile,190,786,180,'Next scene →',true);
const tokens=box(null,3450,0,900,700,C.white,'04 · Design tokens');label(tokens,30,28,'Calm surfaces. Clear decisions.',30,C.ink,830,true);Object.entries(C).forEach(([name,color],i)=>{const x=30+(i%4)*215,y=120+Math.floor(i/4)*210;box(tokens,x,y,185,105,color);label(tokens,x,y+118,`${name}\n${color}`,15,C.ink,200);});label(tokens,30,570,'Body 16px · labels 14px · actions 44px minimum\nColor supplements labels and symbols; it never replaces them.',16,C.muted,830);
cmd('proto.interaction.add',{id:{$ref:reviewLink},dest:{$ref:review}});cmd('proto.interaction.add',{id:{$ref:next},dest:{$ref:review}});cmd('proto.interaction.add',{id:{$ref:fix},dest:{$ref:editor}});
try{
 const result=await call('engine.execute',{command:'command.batch',params:{commands}});
 await call('engine.execute',{command:'file.saveAs',params:{path:join(out,'Showrig-Next.figcraft')}});
 const inspection=await call('document.inspect',{depth:1});writeFileSync(join(out,'inspection.json'),JSON.stringify(inspection,null,2));writeFileSync(join(out,'commands.json'),JSON.stringify(commands,null,2));
 console.log(JSON.stringify({saved:join(out,'Showrig-Next.figcraft'),steps:Array.isArray(result)?result.length:commands.length,inspection}));
}finally{socket.end();}
