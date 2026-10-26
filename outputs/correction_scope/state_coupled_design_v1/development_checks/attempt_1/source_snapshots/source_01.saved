"""Separate scalar float32 stage arithmetic; no call to the main map."""
from struct import pack,unpack

def f32(x):return unpack('<f',pack('<f',float(x)))[0]

def literal(before,command,noise,d):
    x=float(before['current']['observation'][d['axis']])
    if d['kind']=='FLAT_LEFT':w=0.
    elif d['kind']=='FLAT_RIGHT':w=1.
    else:
        value=(x-d['center']+d['half_width'])/(2*d['half_width'])
        if value<0:value=0.
        if value>1:value=1.
        w=3*value*value-2*value*value*value
    a=[[f32(d['left']['matrix_xy'][i][j]+w*(d['right']['matrix_xy'][i][j]-d['left']['matrix_xy'][i][j])) for j in range(2)] for i in range(2)]
    b=[f32(d['left']['bias_xy'][i]+w*(d['right']['bias_xy'][i]-d['left']['bias_xy'][i])) for i in range(2)]
    u=[f32(v) for v in command];transformed=list(u)
    for i in range(2):
        # Each multiplication/addition is rounded separately; BLAS may use a
        # fused dot operation, so the independent check reports its actual gap.
        transformed[i]=f32(f32(f32(a[i][0]*u[0])+f32(a[i][1]*u[1]))+b[i])
        if transformed[i]==0:transformed[i]=0.
    noisy=[f32(transformed[i]+f32(noise[i])) if i<3 else transformed[i] for i in range(4)]
    applied=[max(-1.,min(1.,v)) for v in noisy]
    return dict(state_weight_oracle=w,matrix_xy_oracle=a,bias_xy_oracle=b,
        matrix_det_oracle=a[0][0]*a[1][1]-a[0][1]*a[1][0],transformed_action_oracle=transformed,
        noise_xyz_oracle=[f32(v) for v in noise],before_final_clip_oracle=noisy,
        executed_action_oracle=applied,final_clip_oracle=[abs(v)>1 for v in noisy])
