const navToggle=document.getElementById('navToggle');
const navLinks=document.getElementById('navLinks');
if(navToggle&&navLinks){navToggle.addEventListener('click',()=>navLinks.classList.toggle('open'));}

document.querySelectorAll('.password-toggle').forEach(btn=>{
  btn.addEventListener('click',()=>{
    const input=document.getElementById(btn.dataset.target);
    if(!input)return;
    input.type=input.type==='password'?'text':'password';
    btn.textContent=input.type==='password'?'Show':'Hide';
  });
});

const upload=document.querySelector('input[name="item_picture"]');
const preview=document.getElementById('imagePreview');
if(upload&&preview){
  upload.addEventListener('change',()=>{
    const file=upload.files?.[0];
    if(!file){preview.innerHTML='<span>📷 Your item photo preview appears here.</span>';return;}
    if(file.size>5*1024*1024){alert('Please select an image under 5 MB.');upload.value='';return;}
    const url=URL.createObjectURL(file);
    preview.innerHTML=`<img src="${url}" alt="Selected item photo">`;
  });
}

function updateImpact(){
  const cat=document.querySelector('select[name="category"]');
  const qty=document.querySelector('input[name="quantity"]');
  const factor=document.getElementById('impactFactor');
  const estimate=document.getElementById('impactEstimate');
  if(!cat||!qty||!factor||!estimate||!window.materialFactors)return;
  const f=Number(window.materialFactors[cat.value]||0.4);
  const q=Number(qty.value||0);
  factor.textContent=`${f.toFixed(2)} kg CO₂e/kg*`;
  estimate.textContent=`${(f*q).toFixed(2)} kg CO₂e*`;
}
['change','input'].forEach(event=>document.addEventListener(event,e=>{
  if(e.target?.name==='category'||e.target?.name==='quantity')updateImpact();
}));
updateImpact();
