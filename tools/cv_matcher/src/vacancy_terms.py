"""Literal technology mentions, deliberately separate from skill evidence/fit scoring."""
import re
TERMS=[
 ('torch.compile',r'\btorch\.compile\b'),('PyTorch',r'\bpytorch\b'),('Python',r'\bpython\b'),('Triton',r'\btriton\b'),('vLLM',r'\bvllm\b'),
 ('FSDP',r'\bfsdp\b'),('DeepSpeed',r'\bdeepspeed\b'),('DDP',r'\bddp\b'),('CUDA',r'\bcuda\b'),('MLX',r'\bmlx\b'),('MPS',r'\bmps\b'),
 ('Metal',r'(?<!bare )\bmetal\b'),('TensorRT',r'\btensorrt\b'),('ONNX',r'\bonnx\b'),('FlashAttention',r'\bflash[ -]?attention\b'),
 ('sparse attention',r'\bsparse(?:\s+attention)?\b'),('causal attention',r'\bcausal(?:\s+attention)?\b'),('attention',r'\battention\b'),
 ('DiT',r'\bdit\b'),('VAE',r'\bvae\b'),('Transformer',r'\btransformers?\b|трансформер[а-я]*'),('Diffusion',r'\bdiffusion\b|диффузионн[а-я]*(?:\s+модел[а-я]*)?'),
 ('Flow Matching',r'\bflow[ -]?matching\b'),('RL',r'\brl\b'),('RLHF',r'\brlhf\b'),('DPO',r'\bdpo\b'),('SFT',r'\bsft\b'),
 ('LLM',r'\bllms?\b'),('VLM',r'\bvlms?\b'),('RAG',r'\brag\b'),('quantization',r'\bquantization\b|квантизаци[а-я]*'),('distillation',r'\bdistillation\b|дистилляци[а-я]*'),
 ('distributed training',r'\bdistributed\s+training\b|распредел[её]нн[а-я]*\s+обучени[а-я]*'),('linear algebra',r'\blinear\s+algebra\b|линейн[а-я]*\s+алгебр[а-я]*'),
 ('probability',r'\bprobability\b|теори[а-я]*\s+вероятност[а-я]*'),('statistics',r'\bstatistics\b|статистик[а-я]*'),('optimization',r'\boptimization\b|оптимизаци[а-я]*'),
 ('Docker',r'\bdocker\b'),('Kubernetes',r'\bkubernetes\b|\bk8s\b'),('C++',r'(?<!\w)c\+\+(?!\w)'),('API',r'\bapi\b'),('Git',r'\bgit\b')]

def mentions(cv,jd):
 text='\n'.join([cv.get('title',''),*(s.get('text','') for s in cv.get('sections',[]) if s.get('key') not in ('contacts','contact','personal'))]);result=[]
 for label,pattern in TERMS:
  matches=list(re.finditer(pattern,jd,re.I))
  if not matches:continue
  evidence=re.search(pattern,text,re.I)
  quote=text[max(0,evidence.start()-60):evidence.end()+100].strip() if evidence else ''
  result.append({'label':label,'terms':list(dict.fromkeys(m.group(0) for m in matches)),'in_cv':bool(evidence),'quote':quote})
 return result
