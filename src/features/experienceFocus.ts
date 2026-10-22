import type {Experience, Lang} from '../i18n';
const rules:Record<string,{pattern:RegExp;ru:string;en:string}>={
 vision:{pattern:/diffusion|flow[ -]?matching|\bDiT\b|\bVAE\b|computer vision|opencv|генеративн|диффузион|компьютерн.{0,8}зрен/i,ru:'Генеративные модели / Computer Vision',en:'Generative models / Computer Vision'},
 audio:{pattern:/\bTTS\b|\bASR\b|whisper|tacotron|wave\s?rnn|voice|speech|аудио|реч[ьи]|синтез.{0,8}голос/i,ru:'Аудио / Речь',en:'Audio / Speech'},
 multimodal:{pattern:/multimodal|cross.modal|мультимод|\bCLIP\b|\bCLAP\b|\bVLM\b|text.to.audio|text.to.image|модальност/i,ru:'Мультимодальные системы',en:'Multimodal systems'},
 multiagent:{pattern:/multi.agent|langgraph|agent orchestrat|agentic|мультиагент|многоагент|оркестрац.{0,20}агент/i,ru:'Агенты / Оркестрация',en:'Agents / Orchestration'},
 llm:{pattern:/\bLLM\b|\bNLP\b|transformer|attention|llama|\bGPT\b|\bSFT\b|\bRLHF\b|\bRAG\b|tokeniz|трансформер|языков.{0,8}модел/i,ru:'LLM / NLP',en:'LLM / NLP'},
 ios:{pattern:/\biOS\b|swift|uikit|coreml|objective.c|arkit/i,ru:'iOS / Swift',en:'iOS / Swift'},
};
export function experienceFocus(exp:Pick<Experience,'role'|'company'|'descriptionMd'>,profile:string,lang:Lang):string|null{
 const rule=rules[profile];if(!rule)return null;
 return rule.pattern.test(exp.role+'\n'+exp.company+'\n'+exp.descriptionMd)?(lang==='ru'?rule.ru:rule.en):null;
}
