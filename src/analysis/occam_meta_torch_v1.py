"""Differentiable performance-basis reference. Torch is needed only by training.

Independent implementation from the published model and pinned source review.
No robot data collector, fixed metric, task benefit or full OCCAM claim here.
"""
import torch
from torch import nn


def require(ok,message):
    if not ok:raise ValueError(message)


def tensor(value,ndim):
    require(isinstance(value,torch.Tensor) and value.ndim==ndim and value.dtype in (torch.float32,torch.float64)
        and value.device.type=='cpu' and torch.isfinite(value).all().item(),'finite CPU tensor of declared rank')
    return value


def cov(value,n,positive=False):
    a=tensor(value,2);require(tuple(a.shape)==(n,n) and torch.allclose(a,a.T,atol=1e-10,rtol=0),'symmetric tensor covariance')
    vals=torch.linalg.eigvalsh(a.detach());require((vals.min()>0 if positive else vals.min()>=-1e-10).item(),'SPD measurement / PSD state-process covariance')
    return a


def filter_step(mean,covariance,phi,observed,Q,R):
    mean=tensor(mean,1);p=cov(covariance,len(mean));h=tensor(phi,2);y=tensor(observed,1)
    require(tuple(h.shape)==(len(y),len(mean)),'outputs by bases, not transposed')
    q=cov(Q,len(mean));r=cov(R,len(y),True);predicted=p+q;innovation=y-h@mean
    s=h@predicted@h.T+r;gain=torch.linalg.solve(s,h@predicted).T
    after=mean+gain@innovation;left=torch.eye(len(mean),dtype=mean.dtype)-gain@h
    post=left@predicted@left.T+gain@r@gain.T
    return after,(post+post.T)/2


def mlp(widths):
    modules=[]
    for i in range(len(widths)-1):
        modules.append(nn.Linear(widths[i],widths[i+1],dtype=torch.float64))
        if i<len(widths)-2:modules.append(nn.ReLU())
    return nn.Sequential(*modules)


class PerformanceBasis(nn.Module):
    def __init__(self,history_size,descriptor_size,*,bases,outputs,context_size=16,encoder_hidden=(64,),head_hidden=(256,256,256)):
        super().__init__()
        require(all(type(x) is int and x>0 for x in (history_size,descriptor_size,bases,outputs,context_size)),'positive declared dimensions')
        self.history_size=history_size;self.descriptor_size=descriptor_size;self.bases=bases;self.outputs=outputs
        self.encoder=mlp((history_size,*encoder_hidden,context_size));self.head=mlp((descriptor_size+context_size,*head_hidden,outputs*bases))
        self.prior_mean=nn.Parameter(torch.zeros(bases,dtype=torch.float64))
        self.prior_factor=nn.Parameter(torch.eye(bases,dtype=torch.float64));self.process_factor=nn.Parameter(torch.eye(bases,dtype=torch.float64))
        self.measurement_factor=nn.Parameter(torch.eye(outputs,dtype=torch.float64))

    def forward(self,history,descriptor):
        tensor(history,2);tensor(descriptor,2)
        require(history.shape[0]==descriptor.shape[0] and history.shape[1]==self.history_size and descriptor.shape[1]==self.descriptor_size,'declared feature dimensions')
        return self.head(torch.cat([descriptor,self.encoder(history)],dim=1)).reshape(-1,self.outputs,self.bases)

    def prior(self):
        return self.prior_mean,self.prior_factor@self.prior_factor.T,self.process_factor@self.process_factor.T,self.measurement_factor@self.measurement_factor.T

    def export(self):
        def layers(net):return [dict(weight=m.weight.detach().numpy().tolist(),bias=m.bias.detach().numpy().tolist()) for m in net if isinstance(m,nn.Linear)]
        mean,P,Q,R=self.prior()
        return dict(schema='OCCAM_PERFORMANCE_BASIS_V1',dimensions=dict(history=self.history_size,descriptor=self.descriptor_size,outputs=self.outputs,bases=self.bases),
            encoder=layers(self.encoder),head=layers(self.head),prior=dict(mean=mean.detach().numpy().tolist(),covariance=P.detach().numpy().tolist(),
                process_covariance=Q.detach().numpy().tolist(),measurement_covariance=R.detach().numpy().tolist()))


def meta_loss(model,history,descriptor,targets,support_indices):
    """Adapt on the declared ordered subset, score all rows as in Algorithm1.

    This is an offline meta-training objective, not a chronology certificate.
    A physical protocol must define grouping, support ordering, metrics and cost.
    """
    phi=model(history,descriptor);tensor(targets,2)
    require(tuple(targets.shape)==tuple(phi.shape[:2]) and isinstance(support_indices,(tuple,list)) and len(support_indices)>0
        and len(set(support_indices))==len(support_indices) and all(type(i) is int and 0<=i<len(phi) for i in support_indices),'explicit valid support subset')
    mean,covariance,Q,R=model.prior()
    for i in support_indices:mean,covariance=filter_step(mean,covariance,phi[i],targets[i],Q,R)
    predictions=torch.einsum('tyb,b->ty',phi,mean)
    return ((predictions-targets)**2).mean(),dict(posterior_mean=mean,posterior_covariance=covariance,predictions=predictions)
