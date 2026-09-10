// Adapted from LerSent001/holo-card's WebGL/RGBM renderer (MIT; see LICENSE).
// Material contract: gold-foil-card-studio/references/web-port.md.
const vertex = `attribute vec2 position; varying vec2 uv;
void main(){uv=position*.5+.5;gl_Position=vec4(position,0.,1.);}`;
const hdr = `
vec4 encodeHDR(vec3 c){float m=clamp(ceil(max(max(c.r,c.g),c.b)/64.*255.)/255.,1./255.,1.);return vec4(c/(64.*m),m);}
vec3 decodeHDR(vec4 c){return c.rgb*c.a*64.;}`;
const fragment = `precision highp float;
varying vec2 uv;
uniform sampler2D artwork,lineart,bloomNear,bloomWide;
uniform mat3 mappingRotation;
uniform vec3 camera,goldColor,printInk,printStock;
uniform float cardAspect,emission,repeatCount,phase,noiseScale,noiseAmount,paletteEnabled;
uniform float sweepBlack,sweepWhite,lineBlack,lineWhite,glowPass;
${hdr}
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
// ponytail: stable value noise approximates Blender Noise; use its implementation for exact parity.
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
 return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.)),f.x),f.y);}
vec3 linearize(vec3 c){return mix(c/12.92,pow((c+.055)/1.055,vec3(2.4)),step(vec3(.04045),c));}
vec3 display(vec3 c){return mix(c*12.92,1.055*pow(c,vec3(1./2.4))-.055,step(vec3(.0031308),c));}
void main(){
 // Transparent overscan lets the actual emissive lines glow beyond the card edge.
 vec2 p=uv*vec2(1.2,1.+.2/cardAspect)-vec2(.1,.1/cardAspect);
 vec2 edge=abs((p-.5)*vec2(1.,cardAspect))-vec2(.475,cardAspect*.5-.025);
 float shape=1.-smoothstep(.024,.027,length(max(edge,0.))+min(max(edge.x,edge.y),0.));
 vec3 N=vec3(0.,0.,1.);
 vec3 V=normalize(camera-vec3(p.x-.5,(p.y-.5)*cardAspect,0.));
 vec3 r=mappingRotation*reflect(-V,N);
 float q=(r.x+r.y+r.z)/3.;
 q=(q+noiseAmount*noise(p*noiseScale)+phase)*repeatCount;
 float triangle=1.-abs(mod(q,2.)-1.);
 float sweep=clamp((triangle-sweepBlack)/(sweepWhite-sweepBlack),0.,1.);
 float lineValue=texture2D(lineart,p).r;
 float line=1.-clamp((lineValue-lineBlack)/(lineWhite-lineBlack),0.,1.);
 float mask=sweep*line*shape;
 vec3 art=texture2D(artwork,p).rgb;
 vec3 printColor=paletteEnabled>.5?mix(printInk,printStock,art.r):linearize(art);
 vec3 gold=goldColor*emission;
 if(glowPass>.5){gl_FragColor=encodeHDR(max(gold-1.,0.)*mask);return;}
 vec3 color=mix(printColor,gold,sweep*line*(emission>0.?1.:0.));
 vec3 bloom=decodeHDR(texture2D(bloomNear,uv))*.3+decodeHDR(texture2D(bloomWide,uv))*.4;
 // Emissive highlight compression after linear mixing, not Blender AgX.
 vec3 highlight=max(color-printColor,0.)+bloom;
 vec3 mapped=min(color,printColor)+(1.-min(color,printColor))*(1.-exp(-highlight*.65));
 vec3 halo=display(1.-exp(-bloom*.8));
 float haloAlpha=max(max(halo.r,halo.g),halo.b);
 float alpha=shape+(1.-shape)*haloAlpha;
 vec3 premult=mix(halo,display(clamp(mapped,0.,1.)),shape);
 // Keep RGB premultiplied through WebKit/Core Animation, including low-alpha bloom.
 gl_FragColor=vec4(premult,alpha);
}`;
const blurFragment = `precision highp float; varying vec2 uv;uniform sampler2D source;uniform vec2 stepSize;
${hdr}
void main(){vec3 c=vec3(0.);float total=0.;for(int i=-4;i<=4;i++){float f=float(i);float w=exp(-f*f/8.);c+=decodeHDR(texture2D(source,uv+stepSize*f))*w;total+=w;}gl_FragColor=encodeHDR(c/total);}`;

// Inverse of the viewer's CSS Rx * Ry, with CSS's downward Y converted to UV's upward Y.
export function localCamera(x, y, distance) {
  const rx=x*Math.PI/180, ry=y*Math.PI/180;
  return [-Math.sin(ry)*Math.cos(rx)*distance, -Math.sin(rx)*distance, Math.cos(ry)*Math.cos(rx)*distance];
}
export function rotationMatrix(degrees) {
  const [x,y,z]=degrees.map(v=>v*Math.PI/180), a=Math.cos(x),b=Math.sin(x),c=Math.cos(y),d=Math.sin(y),e=Math.cos(z),f=Math.sin(z);
  return [e*c,f*c,-d, e*d*b-f*a,f*d*b+e*a,c*b, e*d*a+f*b,f*d*a-e*b,c*a];
}

export async function createCardRenderer(canvas, config) {
  const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:false,preserveDrawingBuffer:true});
  if(!gl)throw new Error('此浏览器不支持 WebGL');
  const shaders=[],programs=[],textures=[],frames=[];
  const buffer=gl.createBuffer();
  const dispose=()=>{
    frames.forEach(f=>gl.deleteFramebuffer(f));textures.forEach(t=>gl.deleteTexture(t));
    shaders.forEach(s=>gl.deleteShader(s));programs.forEach(p=>gl.deleteProgram(p));gl.deleteBuffer(buffer);
  };
  try {
    gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);
    function compile(type,source){
      const s=gl.createShader(type);shaders.push(s);gl.shaderSource(s,source);gl.compileShader(s);
      if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;
    }
    function program(source){
      const p=gl.createProgram();programs.push(p);gl.attachShader(p,compile(gl.VERTEX_SHADER,vertex));
      gl.attachShader(p,compile(gl.FRAGMENT_SHADER,source));gl.linkProgram(p);
      if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(p));return p;
    }
    const scene=program(fragment),blur=program(blurFragment);
    function use(p){gl.useProgram(p);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);const a=gl.getAttribLocation(p,'position');gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,2,gl.FLOAT,false,0,0);}
    function texture(filter){
      const t=gl.createTexture();textures.push(t);gl.bindTexture(gl.TEXTURE_2D,t);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,filter);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,filter);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);return t;
    }
    const images=await Promise.all(['artwork','lineart'].map(name=>new Promise((resolve,reject)=>{
      const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error(`${name} 纹理加载失败`));img.src=config.assets[name];
    })));
    if(images[0].width!==images[1].width||images[0].height!==images[1].height)throw new Error('卡面和线稿尺寸不一致');
    const artTextures=images.map(img=>{
      const t=texture(gl.LINEAR);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);
      gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL,gl.NONE);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,img);return t;
    });
    const aspect=images[0].height/images[0].width;
    const cardWidth=innerWidth<640?648:880;
    canvas.width=Math.round(cardWidth*1.2);canvas.height=Math.round(cardWidth*(aspect+.2));
    function target(scale){
      const w=Math.round(canvas.width*scale),h=Math.round(canvas.height*scale),t=texture(gl.LINEAR);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,w,h,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
      const f=gl.createFramebuffer();frames.push(f);gl.bindFramebuffer(gl.FRAMEBUFFER,f);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,t,0);
      if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw new Error('辉光缓冲区不可用');return {t,f,w,h};
    }
    const light=target(.5),temp=target(.5),near=target(.5),wideTemp=target(.25),wide=target(.25);
    const u=Object.fromEntries(['camera','emission','repeatCount','glowPass'].map(n=>[n,gl.getUniformLocation(scene,n)]));
    use(scene);
    gl.uniform1f(gl.getUniformLocation(scene,'cardAspect'),aspect);
    for(const n of ['phase','noiseScale','noiseAmount','sweepBlack','sweepWhite','lineBlack','lineWhite'])gl.uniform1f(gl.getUniformLocation(scene,n),config.gold[n]);
    gl.uniform3fv(gl.getUniformLocation(scene,'goldColor'),config.gold.color);
    gl.uniform1f(gl.getUniformLocation(scene,'paletteEnabled'),config.printPalette?1:0);
    gl.uniform3fv(gl.getUniformLocation(scene,'printInk'),config.printPalette?.ink??[0,0,0]);
    gl.uniform3fv(gl.getUniformLocation(scene,'printStock'),config.printPalette?.stock??[1,1,1]);
    gl.uniformMatrix3fv(gl.getUniformLocation(scene,'mappingRotation'),false,rotationMatrix(config.gold.mappingRotation));
    ['artwork','lineart','bloomNear','bloomWide'].forEach((n,i)=>gl.uniform1i(gl.getUniformLocation(scene,n),i));
    use(blur);gl.uniform1i(gl.getUniformLocation(blur,'source'),0);const step=gl.getUniformLocation(blur,'stepSize');
    function bind(t,unit=0){gl.activeTexture(gl.TEXTURE0+unit);gl.bindTexture(gl.TEXTURE_2D,t);}
    function blurPass(src,dst,x,y){use(blur);bind(src.t);gl.bindFramebuffer(gl.FRAMEBUFFER,dst.f);gl.viewport(0,0,dst.w,dst.h);gl.uniform2f(step,x/src.w,y/src.h);gl.drawArrays(gl.TRIANGLES,0,6);}
    function bindScene(){use(scene);[...artTextures,near.t,wide.t].forEach((t,i)=>bind(t,i));}
    return {
      aspect,
      draw(x,y,emission,repeat,distance){
        bindScene();gl.uniform3fv(u.camera,localCamera(x,y,distance));
        gl.uniform1f(u.emission,emission);gl.uniform1f(u.repeatCount,repeat);gl.uniform1f(u.glowPass,1);
        gl.bindFramebuffer(gl.FRAMEBUFFER,light.f);gl.viewport(0,0,light.w,light.h);gl.drawArrays(gl.TRIANGLES,0,6);
        blurPass(light,temp,1.2,0);blurPass(temp,near,0,1.2);blurPass(near,wideTemp,5,0);blurPass(wideTemp,wide,0,2.5);
        bindScene();gl.uniform1f(u.glowPass,0);gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,canvas.width,canvas.height);gl.drawArrays(gl.TRIANGLES,0,6);
        if(gl.getError()!==gl.NO_ERROR)throw new Error('WebGL 绘制失败');
      },dispose
    };
  } catch(error){dispose();throw error;}
}
