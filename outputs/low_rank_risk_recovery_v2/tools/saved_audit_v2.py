"""Certify saved ridge/spectral solutions without any fitting or decomposition."""
from contextlib import contextmanager, ExitStack
from unittest import mock
import numpy as np


def need(ok,msg):
    if not ok:raise ValueError('saved certificate: '+msg)


def close(a,b,msg,tol=1e-7):
    a=np.asarray(a);b=np.asarray(b)
    need(a.shape==b.shape and np.isfinite(a).all() and np.isfinite(b).all(),msg+' finite shape')
    delta=float(np.max(np.abs(a-b))) if a.size else 0.
    need(delta<=tol,msg);return delta


def coordinates():
    columns=[]
    for j in range(11):
        v=np.array([int(k==j)-int(k==11) for k in range(12)],float)
        for b in columns:v=v-np.sum(v*b)*b
        columns.append(v/np.sqrt(np.sum(v*v)))
    return np.stack(columns,axis=1)


def kernel(a,b,kind):
    d=max(1,a.shape[1])
    if kind=='LINEAR':return a@b.T/d
    need(kind=='RBF','declared kernel')
    distance=np.maximum(np.sum(a*a,axis=1)[:,None]+np.sum(b*b,axis=1)[None,:]-2*a@b.T,0)/d
    return np.exp(-distance/2)


def spectral(matrix,values,basis,contrast,msg):
    d=coordinates() if contrast else np.eye(12)
    close(basis.T@basis,np.eye(d.shape[1]),msg+' orthonormal')
    close(d@d.T@basis,basis,msg+' supported subspace')
    need(values.shape==(d.shape[1],) and np.all(values[:-1]>=values[1:]-1e-10),'ordered spectrum '+msg)
    close((d@d.T)@matrix@basis,basis*values,msg+' full eigen equation')


def certificate(saved,x,y,groups,kind,training_ids):
    n=len(x);gs=sorted(set(map(int,groups)))
    w=np.array([n/(len(gs)*sum(int(v==g) for v in groups)) for g in groups]);p=w/sum(w)
    active=np.where(np.max(x,axis=0)!=np.min(x,axis=0))[0]
    mean=np.sum(x[:,active]*p[:,None],axis=0)
    scale=np.maximum(.05,np.sqrt(np.sum((x[:,active]-mean)**2*p[:,None],axis=0)))
    need(np.array_equal(saved['active'],active) and np.array_equal(saved['training_unit_indices'],training_ids),'training identity and active coordinates')
    close(saved['mean'],mean,'train-only means',1e-10);close(saved['scale'],scale,'train-only scale',1e-10)
    close(saved['weights'],w,'group weights',1e-10)
    z=np.minimum(10,np.maximum(-10,(x[:,active]-mean)/scale));close(saved['centers'],z,'training centers',1e-10)
    k=kernel(z,z,kind);kc=k-(p@k)[None,:]-(k@p)[:,None]+float(p@k@p)
    close(saved['k'],k,'kernel');close(saved['kc'],kc,'centered kernel')
    close(saved['kernel_mean'],p@k,'kernel mean');close(saved['kernel_grand'],np.array([p@k@p]),'kernel grand')
    ym=p@y;yc=y-ym;close(saved['target_mean'],ym,'unpenalized column intercept')
    fitted=kc@saved['alpha']
    stationarity=close(fitted+.01*saved['alpha']/w[:,None],yc,'ridge stationarity')
    close(np.sum(saved['alpha'],axis=0),np.zeros(12),'unweighted dual intercept constraint')
    raw=yc.T@(w[:,None]*fitted);raw=(raw+raw.T)/2
    spectral(raw,saved['raw_eigenvalues'],saved['raw_basis'],False,'predictive raw')
    spectral(raw,saved['rr_eigenvalues'],saved['rr_basis'],True,'predictive contrast')
    covariance=yc.T@(w[:,None]*yc)
    spectral(covariance,saved['pca_eigenvalues'],saved['pca_basis'],True,'target PCA')
    for name,rank,mode in [('FULL',12,'FULL'),*[(f'RR{r}',r,'rr') for r in (1,2,4)],
                         *[(f'PCA{r}',r,'pca') for r in (1,2,4)],('RAW_RR2',2,'raw'),('RAW_RR3',3,'raw')]:
        if mode=='FULL':project=np.eye(12)
        else:
            b=saved[mode+'_basis'];project=b[:,:rank]@b[:,:rank].T
            if mode!='raw':project+=np.ones((12,12))/12
        stored=saved['projection_'+kind+'_'+name]
        close(stored,project,'fixed projection '+name);close(stored@stored,stored,'idempotent projection '+name)
        close(stored.T,stored,'symmetric projection '+name)
    return dict(ridge_stationarity_max_abs=stationarity,spectral_certificates=3,projection_certificates=9)


def prediction(saved,x,kind,projection):
    z=np.minimum(10,np.maximum(-10,(x[:,saved['active']]-saved['mean'])/saved['scale']))
    k=kernel(z,saved['centers'],kind);p=saved['weights']/sum(saved['weights'])
    # Different multiplication association from the original predictor.
    centered=k-saved['kernel_mean']-(k@p)[:,None]+saved['kernel_grand'][0]
    return ((centered@saved['alpha'])@projection)+saved['target_mean']


@contextmanager
def no_fit():
    def deny(*args,**kwargs):raise RuntimeError('saved-model recovery forbids fitting/decomposition')
    with ExitStack() as stack:
        for name in ('solve','lstsq','eig','eigh','eigvals','eigvalsh','svd','qr','cholesky','inv','pinv'):
            stack.enter_context(mock.patch.object(np.linalg,name,deny))
        yield
