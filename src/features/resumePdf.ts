import type {CVContent,Lang} from '../i18n';
import type {HHSnapshot} from './hhExperience';

const plain=(value:string)=>value.replace(/<[^>]+>/g,' ').replace(/\*\*/g,'').trim();
export function resumePDFDefinition(cv:CVContent,lang:Lang,snapshot:HHSnapshot|null,portrait?:string){
 const ru=lang==='ru';
 const heading=(text:string)=>({text,style:'section',keepWithHeaderRows:1});
 const header:unknown[]=[
  {text:cv.name,style:'name'},
  {text:plain(cv.title.split(/<br/i)[0]),style:'role'},
  {text:cv.contact.email,link:'mailto:'+cv.contact.email,style:'link'},
  {text:[{text:'GitHub',link:'https://github.com/vladislav-vasilenko'},' · ',{text:'Hugging Face',link:'https://huggingface.co/VVladTech'},' · ',{text:'LinkedIn',link:'https://linkedin.com/in/tech'},' · ',{text:'Telegram',link:'https://t.me/vsvladis'}],style:'link',margin:[0,4,0,12]},
 ];
 const content:unknown[]=portrait?[{columns:[{width:'*',stack:header},{image:portrait,fit:[112,148],width:112}],columnGap:20}]:header;
 if(snapshot?.source.url)content.push({text:[ru?'Источник: ':'Source: ',{text:ru?'основное HH-резюме':'primary HH resume',link:snapshot.source.url}],fontSize:9,color:'#64716c'});
 content.push(heading(ru?'Обо мне':'About'),{text:snapshot?.about?.translations?.[lang]||snapshot?.about?.text||cv.aboutMd});
 content.push(heading(ru?'Опыт работы':'Work experience'));
 for(const job of cv.experience)content.push({columns:[{width:92,text:job.period+'\n'+job.duration,fontSize:9,color:'#64716c'},{width:'*',stack:[{text:job.company,bold:true,fontSize:11},{text:job.role,bold:true,margin:[0,3,0,7]},{text:plain(job.descriptionMd)}]}],columnGap:16,margin:[0,7,0,14]});
 if(snapshot?.confirmed_skills.length){
  content.push(heading(ru?'Подтверждённые навыки':'Skills with evidence'));
  for(const skill of snapshot.confirmed_skills)content.push({text:[{text:skill.label,bold:true},...skill.links.flatMap(link=>[' · ',{text:link.label,link:link.url}])],margin:[0,3,0,3]});
 }
 content.push(heading(ru?'Навыки и инструменты':'Skills and tools'));
 for(const category of cv.techStack.categories)content.push({text:[{text:category.label[lang]+': ',bold:true},category.items.map(item=>item.name).join(', ')],margin:[0,3,0,3]});
 content.push(heading(ru?'Образование и курсы':'Education and courses'));
 for(const item of cv.education)content.push({text:[{text:item.year+' · '+item.institution,bold:true},'\n'+item.program],margin:[0,4,0,7]});
 if(cv.languages?.length)content.push(heading(ru?'Языки':'Languages'),{text:cv.languages.join(' · ')});
 return {pageSize:'A4',pageMargins:[38,36,38,38],info:{title:cv.name+' — CV',author:cv.name},defaultStyle:{font:'Roboto',fontSize:10,lineHeight:1.25,color:'#20332c'},styles:{name:{fontSize:24,bold:true,margin:[0,0,0,8]},role:{fontSize:13,margin:[0,0,0,10]},section:{fontSize:14,bold:true,margin:[0,17,0,9]},link:{color:'#245b91',fontSize:10}},content};
}

/** Generates a real, local PDF; no print dialog, popup or external conversion service. */
export async function downloadResumePDF(cv:CVContent,lang:Lang,snapshot:HHSnapshot|null):Promise<void>{
 const [{default:pdfMake},{default:fonts}]=await Promise.all([import('pdfmake/build/pdfmake'),import('pdfmake/build/vfs_fonts')]);
 pdfMake.addVirtualFileSystem(fonts);
 let portrait:string|undefined;
 try{
  const response=await fetch('/profile.jpg',{cache:'force-cache'});
  if(response.ok){
   const blob=await response.blob();
   if(blob.size<3000000)portrait=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=reject;reader.readAsDataURL(blob);});
  }
 }catch{/* The complete text PDF remains available if the public photo is offline. */}
 await pdfMake.createPdf(resumePDFDefinition(cv,lang,snapshot,portrait)).download(`Vladislav_Vasilenko_CV_${lang.toUpperCase()}.pdf`);
}
