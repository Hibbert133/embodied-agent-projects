"""Independent whole-sequence Gaussian conditioning, not recursive KF replay."""
import numpy as np


def batch_posterior(mean,cov,phis,observed,process_cov,measurement_cov):
    mean=np.asarray(mean,float);P=np.asarray(cov,float);Q=np.asarray(process_cov,float);R=np.asarray(measurement_cov,float)
    H=[np.asarray(x,float) for x in phis];Y=[np.asarray(y,float) for y in observed];n=len(H)
    if not n:return mean.copy(),P.copy()
    d=R.shape[0];blocks=np.empty((n*d,n*d));cross=np.empty((len(mean),n*d))
    for i in range(n):
        cross[:,i*d:(i+1)*d]=(P+(i+1)*Q)@H[i].T
        for j in range(n):
            blocks[i*d:(i+1)*d,j*d:(j+1)*d]=H[i]@(P+min(i+1,j+1)*Q)@H[j].T+(R if i==j else 0.)
    residual=np.concatenate([Y[i]-H[i]@mean for i in range(n)])
    solved=np.linalg.solve(blocks,np.column_stack([residual,cross.T]));gain_effect=cross@solved
    return mean+gain_effect[:,0],P+n*Q-gain_effect[:,1:]
