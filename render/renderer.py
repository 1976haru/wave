from __future__ import annotations
import numpy as np

def parse_color(value):
    value=str(value or "#FFFFFF").lstrip("#")
    if len(value)!=6:value="FFFFFF"
    return np.array([int(value[i:i+2],16) for i in (0,2,4)],np.float32)
def gradient_colors(template,count):
    start=parse_color(template.get("gradient_start") or template.get("color","#FFFFFF"));end=parse_color(template.get("gradient_end") or template.get("color","#FFFFFF"));enabled=bool(template.get("gradient"))
    if not enabled:end=start
    return np.linspace(start,end,max(1,count)).astype(np.uint8)
def _geometry(w,h,values,t):
    usable=max(1,int(w*float(t.get("width",.72))));x0=(w-usable)//2;step=usable/max(1,len(values));base={"top":int(h*.18),"center":int(h*.5),"bottom":int(h*.82)}.get(t.get("position","bottom"),int(h*.82));maximum=max(1,int(h*float(t.get("height",.22))));gap=np.clip(float(t.get("gap",.45)),0,.95);width=max(1,int(step*float(t.get("bar_width",1-gap))));return x0,step,base,maximum,width

def build_line_vertices(w,h,values,template,mirror=False):
    """Return a connected miter-style triangle strip in pixel coordinates."""
    values=np.asarray(values,np.float32);x0,step,base,maximum,thickness=_geometry(w,h,values,template);x=x0+(np.arange(len(values))+.5)*step;y=base-values*maximum
    if mirror:y=base+values*maximum
    points=np.column_stack((x,y));colors=gradient_colors(template,len(values)).astype(np.float32)/255
    if len(points)<2:return np.empty((0,5),np.float32)
    tangent=np.empty_like(points);tangent[0]=points[1]-points[0];tangent[-1]=points[-1]-points[-2];tangent[1:-1]=points[2:]-points[:-2];length=np.maximum(np.linalg.norm(tangent,axis=1,keepdims=True),1e-6);tangent/=length;normal=np.column_stack((-tangent[:,1],tangent[:,0]))*(max(1,thickness)/2);left=points+normal;right=points-normal;vertices=np.empty((len(points)*2,5),np.float32);vertices[0::2,:2]=left;vertices[1::2,:2]=right;vertices[0::2,2:]=colors;vertices[1::2,2:]=colors;return vertices

class CPURenderer:
    name="CPU"
    def render_rgba(self,w,h,state,template):
        try:import cv2
        except ImportError:return self._numpy(w,h,state,template)
        values=np.asarray(state["values"],np.float32);x0,step,base,maximum,bw=_geometry(w,h,values,template);colors=gradient_colors(template,len(values));opacity=int(255*np.clip(float(template.get("opacity",1)),0,1));style=str(template.get("renderer",template.get("style","bars"))).lower();rgb=np.zeros((h,w,3),np.uint8);alpha=np.zeros((h,w),np.uint8);mirror=bool(template.get("mirror"));points=[]
        def bar(x,a,color,down=False):
            y1,y2=(base,min(h-1,base+a)) if down else (max(0,base-a),base);radius=int(min(bw/2,a/2)*np.clip(float(template.get("roundness",0)),0,1));cv2.rectangle(rgb,(x-bw//2,y1),(x+bw//2,y2),tuple(map(int,color)),-1,cv2.LINE_AA);cv2.rectangle(alpha,(x-bw//2,y1),(x+bw//2,y2),opacity,-1,cv2.LINE_AA)
            if radius:cy=y2 if down else y1;cv2.circle(rgb,(x,cy),bw//2,tuple(map(int,color)),-1,cv2.LINE_AA);cv2.circle(alpha,(x,cy),bw//2,opacity,-1,cv2.LINE_AA)
        for i,value in enumerate(values):
            amplitude=max(1,int(float(value)*maximum));x=int(x0+(i+.5)*step);points.append((x,base-amplitude))
            if style=="bars":bar(x,amplitude,colors[i]);mirror and bar(x,amplitude,colors[i],True)
            elif style=="dot":
                radius=max(1,bw//2);cv2.circle(rgb,(x,base-amplitude),radius,tuple(map(int,colors[i])),-1,cv2.LINE_AA);cv2.circle(alpha,(x,base-amplitude),radius,opacity,-1,cv2.LINE_AA)
                if mirror:cv2.circle(rgb,(x,base+amplitude),radius,tuple(map(int,colors[i])),-1,cv2.LINE_AA);cv2.circle(alpha,(x,base+amplitude),radius,opacity,-1,cv2.LINE_AA)
        if style=="line" and len(points)>1:
            thickness=max(1,bw)
            for i,(a,b) in enumerate(zip(points[:-1],points[1:])):
                color=tuple(map(int,colors[i]));cv2.line(rgb,a,b,color,thickness,cv2.LINE_AA);cv2.line(alpha,a,b,opacity,thickness,cv2.LINE_AA)
                if mirror:ma=(a[0],2*base-a[1]);mb=(b[0],2*base-b[1]);cv2.line(rgb,ma,mb,color,thickness,cv2.LINE_AA);cv2.line(alpha,ma,mb,opacity,thickness,cv2.LINE_AA)
        if template.get("shadow"):
            shadow=cv2.GaussianBlur(alpha,(0,0),max(1,float(template.get("glow_radius",10))/2));alpha=np.maximum(alpha,(shadow*.25).astype(np.uint8))
        if template.get("glow"):
            radius=max(.1,float(template.get("glow_radius",10)));strength=max(0,float(template.get("glow_strength",.55)));ga=cv2.GaussianBlur(alpha,(0,0),radius);gr=cv2.GaussianBlur(rgb,(0,0),radius);alpha=np.maximum(alpha,np.clip(ga*strength,0,255).astype(np.uint8));rgb=np.clip(rgb.astype(np.float32)+gr.astype(np.float32)*strength,0,255).astype(np.uint8)
        return np.dstack((rgb,alpha))
    def _numpy(self,w,h,state,t):
        out=np.zeros((h,w,4),np.uint8);values=np.asarray(state["values"]);x0,step,base,maximum,bw=_geometry(w,h,values,t);colors=gradient_colors(t,len(values));opacity=int(255*float(t.get("opacity",1)))
        for i,v in enumerate(values):
            a=max(1,int(v*maximum));x=int(x0+(i+.5)*step);xa,xb=max(0,x-bw//2),min(w,x+bw//2+1);out[max(0,base-a):base+1,xa:xb,:3]=colors[i];out[max(0,base-a):base+1,xa:xb,3]=opacity
            if t.get("mirror"):out[base:min(h,base+a),xa:xb,:3]=colors[i];out[base:min(h,base+a),xa:xb,3]=opacity
        return out

class GPUBarRenderer:
    """ModernGL waveform renderer with connected lines and two-pass GPU glow."""
    name="GPU"
    def __init__(self):
        import moderngl
        self.gl=moderngl;self.ctx=moderngl.create_standalone_context(require=330);self.quad=self.ctx.buffer(np.array([[0,0],[1,0],[0,1],[1,1]],"f4").tobytes());self.screen=self.ctx.buffer(np.array([[-1,-1],[1,-1],[-1,1],[1,1]],"f4").tobytes())
        self.shape_program=self.ctx.program(vertex_shader='''#version 330
in vec2 corner;in vec4 rect;in vec3 instance_color;uniform vec2 viewport;out vec2 uv;out vec3 vcolor;
void main(){uv=corner;vcolor=instance_color;vec2 p=rect.xy+(corner-.5)*rect.zw;gl_Position=vec4(p/viewport*2.0-1.0,0,1);}''',fragment_shader='''#version 330
in vec2 uv;in vec3 vcolor;uniform float opacity;uniform int shape;uniform float roundness;out vec4 frag;
void main(){float a=opacity;if(shape==1)a*=smoothstep(.52,.44,length(uv-.5));else if(roundness>0.0){vec2 q=abs(uv-.5)-vec2(.5-roundness*.45);a*=1.0-smoothstep(roundness*.44,roundness*.5,length(max(q,0.0)));}frag=vec4(vcolor,a);}''')
        self.line_program=self.ctx.program(vertex_shader='''#version 330
in vec2 position;in vec3 vertex_color;uniform vec2 viewport;out vec3 vcolor;
void main(){vcolor=vertex_color;vec2 p=vec2(position.x,viewport.y-position.y);gl_Position=vec4(p/viewport*2.0-1.0,0,1);}''',fragment_shader='''#version 330
in vec3 vcolor;uniform float opacity;out vec4 frag;void main(){frag=vec4(vcolor,opacity);}''')
        self.blur_program=self.ctx.program(vertex_shader='''#version 330
in vec2 position;out vec2 uv;void main(){uv=position*.5+.5;gl_Position=vec4(position,0,1);}''',fragment_shader='''#version 330
uniform sampler2D source;uniform vec2 direction;in vec2 uv;out vec4 frag;
void main(){vec4 c=texture(source,uv)*.227027;c+=texture(source,uv+direction*1.384615)*.316216;c+=texture(source,uv-direction*1.384615)*.316216;c+=texture(source,uv+direction*3.230769)*.070270;c+=texture(source,uv-direction*3.230769)*.070270;frag=c;}''')
        self.composite_program=self.ctx.program(vertex_shader='''#version 330
in vec2 position;out vec2 uv;void main(){uv=position*.5+.5;gl_Position=vec4(position,0,1);}''',fragment_shader='''#version 330
uniform sampler2D original;uniform sampler2D glow;uniform float strength;in vec2 uv;out vec4 frag;
void main(){vec4 a=texture(original,uv);vec4 g=texture(glow,uv)*strength;frag=vec4(min(a.rgb+g.rgb,vec3(1)),max(a.a,g.a));}''')
        self.blur_vao=self.ctx.simple_vertex_array(self.blur_program,self.screen,"position");self.composite_vao=self.ctx.simple_vertex_array(self.composite_program,self.screen,"position")
    def available(self):return True
    def _draw_shapes(self,w,h,values,t):
        x0,step,base,maximum,bw=_geometry(w,h,values,t);mirror=bool(t.get("mirror"));rects=[];colors=[]
        for i,v in enumerate(values):
            amplitude=max(1,float(v)*maximum);cx=x0+(i+.5)*step;style=t.get("renderer","bars")
            if style=="dot":rects.append((cx,h-(base-amplitude),bw,bw))
            else:rects.append((cx,h-base+amplitude/2,bw,amplitude))
            colors.append(gradient_colors(t,len(values))[i]/255)
            if mirror:
                if style=="dot":rects.append((cx,h-(base+amplitude),bw,bw))
                else:rects.append((cx,h-base-amplitude/2,bw,amplitude))
                colors.append(gradient_colors(t,len(values))[i]/255)
        rb=self.ctx.buffer(np.asarray(rects,"f4").tobytes());cb=self.ctx.buffer(np.asarray(colors,"f4").tobytes());vao=self.ctx.vertex_array(self.shape_program,[(self.quad,"2f","corner"),(rb,"4f/i","rect"),(cb,"3f/i","instance_color")]);self.shape_program["viewport"].value=(w,h);self.shape_program["opacity"].value=float(t.get("opacity",1));self.shape_program["shape"].value=1 if t.get("renderer")=="dot" else 0;self.shape_program["roundness"].value=float(t.get("roundness",0));vao.render(self.gl.TRIANGLE_STRIP,instances=len(rects));vao.release();rb.release();cb.release()
    def _draw_line(self,w,h,values,t):
        for mirror in ([False,True] if t.get("mirror") else [False]):
            vertices=build_line_vertices(w,h,values,t,mirror)
            if not len(vertices):continue
            buffer=self.ctx.buffer(vertices.tobytes());vao=self.ctx.vertex_array(self.line_program,[(buffer,"2f 3f","position","vertex_color")]);self.line_program["viewport"].value=(w,h);self.line_program["opacity"].value=float(t.get("opacity",1));vao.render(self.gl.TRIANGLE_STRIP);vao.release();buffer.release()
    def _gpu_glow(self,w,h,original,strength,radius):
        textures=[self.ctx.texture((w,h),4,dtype="f1") for _ in range(3)];fbos=[self.ctx.framebuffer([tex]) for tex in textures];original.use(0);self.blur_program["source"].value=0;fbos[0].use();self.blur_program["direction"].value=(max(1,radius)/w,0);self.blur_vao.render(self.gl.TRIANGLE_STRIP);textures[0].use(0);fbos[1].use();self.blur_program["direction"].value=(0,max(1,radius)/h);self.blur_vao.render(self.gl.TRIANGLE_STRIP);original.use(0);textures[1].use(1);fbos[2].use();self.composite_program["original"].value=0;self.composite_program["glow"].value=1;self.composite_program["strength"].value=float(strength);self.composite_vao.render(self.gl.TRIANGLE_STRIP);return textures,fbos,textures[2]
    def render_rgba(self,w,h,state,t):
        values=np.asarray(state["values"],"f4");base=self.ctx.texture((w,h),4,dtype="f1");base.filter=(self.gl.LINEAR,self.gl.LINEAR);fbo=self.ctx.framebuffer([base]);fbo.use();self.ctx.clear(0,0,0,0);self.ctx.enable(self.gl.BLEND);self.ctx.blend_func=(self.gl.SRC_ALPHA,self.gl.ONE_MINUS_SRC_ALPHA)
        if t.get("renderer")=="line":self._draw_line(w,h,values,t)
        else:self._draw_shapes(w,h,values,t)
        resources=[];output=base
        if t.get("glow"):
            textures,fbos,output=self._gpu_glow(w,h,base,float(t.get("glow_strength",.55)),float(t.get("glow_radius",10)));resources=(textures,fbos)
        data=np.frombuffer(output.read(alignment=1),np.uint8).reshape(h,w,4);fbo.release();base.release()
        if resources:
            for item in resources[1]:item.release()
            for item in resources[0]:item.release()
        return np.flipud(data).copy()

class AutoRenderer:
    name="GPU"
    def __init__(self):
        self.cpu=CPURenderer()
        try:self.active=GPUBarRenderer()
        except Exception:self.active=self.cpu;self.name="CPU"
    def render_rgba(self,w,h,state,template):
        try:return self.active.render_rgba(w,h,state,template)
        except Exception:
            self.active=self.cpu;self.name="CPU";return self.cpu.render_rgba(w,h,state,template)
class RendererFactory:
    @staticmethod
    def create(choice="AUTO"):
        choice=choice.upper()
        if choice=="AUTO":return AutoRenderer()
        if choice=="GPU":return GPUBarRenderer()
        return CPURenderer()
