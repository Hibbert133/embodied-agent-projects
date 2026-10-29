"""Pure arrays only, no real model/graph reads and no fitting."""
import copy
import unittest
import numpy as np
import saved_audit_v1 as a


def fixture(kind='LINEAR'):
    x=np.array([[0.],[1.]]);y=np.tile(np.arange(12)/20,(2,1));g=np.array([0,1]);d=a.coordinates()
    z=np.array([[-1.],[1.]]);k=a.kernel(z,z,kind)
    s=dict(active=np.array([0]),training_unit_indices=np.array([10,11]),mean=np.array([.5]),scale=np.array([.5]),
        centers=z,weights=np.ones(2),k=k,kc=k-k.mean(0)-k.mean(1)[:,None]+k.mean(),kernel_mean=k.mean(0),
        kernel_grand=np.array([k.mean()]),target_mean=y[0],alpha=np.zeros((2,12)),
        raw_eigenvalues=np.zeros(12),raw_basis=np.eye(12),rr_eigenvalues=np.zeros(11),rr_basis=d,
        pca_eigenvalues=np.zeros(11),pca_basis=d)
    for name,r,mode in [('FULL',12,'FULL'),*[(f'RR{r}',r,'rr') for r in (1,2,4)],
                       *[(f'PCA{r}',r,'pca') for r in (1,2,4)],('RAW_RR2',2,'raw'),('RAW_RR3',3,'raw')]:
        b=s.get(mode+'_basis');p=np.eye(12) if mode=='FULL' else b[:,:r]@b[:,:r].T
        if mode not in ('FULL','raw'):p+=np.ones((12,12))/12
        s['projection_'+kind+'_'+name]=p
    return s,x,y,g


class Checks(unittest.TestCase):
    def verify(self,s,x,y,g,kind='LINEAR'):
        with a.no_fit():return a.certificate(s,x,y,g,kind,np.array([10,11]))
    def test_linear_certificate_without_fit(self):self.assertEqual(self.verify(*fixture())['projection_certificates'],9)
    def test_rbf_certificate_without_fit(self):self.verify(*fixture('RBF'),kind='RBF')
    def test_changed_coefficients_rejected(self):
        s,x,y,g=fixture();s['alpha'][0,0]=.1
        with self.assertRaises(ValueError):self.verify(s,x,y,g)
    def test_future_group_normalization_rejected(self):
        s,x,y,g=fixture();s['mean'][0]=.6
        with self.assertRaises(ValueError):self.verify(s,x,y,g)
    def test_fold_identity_rejected(self):
        s,x,y,g=fixture();s['training_unit_indices'][0]=99
        with self.assertRaises(ValueError):self.verify(s,x,y,g)
    def test_bad_eigenvalue_rejected(self):
        s,x,y,g=fixture();s['raw_eigenvalues'][0]=.2
        with self.assertRaises(ValueError):self.verify(s,x,y,g)
    def test_common_direction_in_contrast_rejected(self):
        s,x,y,g=fixture();s['rr_basis'][:,0]=np.ones(12)/np.sqrt(12)
        with self.assertRaises(ValueError):self.verify(s,x,y,g)
    def test_changed_projection_rejected(self):
        s,x,y,g=fixture();s['projection_LINEAR_RR2'][0,0]+=.1
        with self.assertRaises(ValueError):self.verify(s,x,y,g)
    def test_prediction_constant_targets(self):
        s,x,y,g=fixture()
        with a.no_fit():a.close(a.prediction(s,x,'LINEAR',s['projection_LINEAR_RR2']),y,'constant prediction')
    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):a.close(np.array([np.nan]),np.array([0.]),'nan')
    def test_all_fit_paths_blocked(self):
        with a.no_fit():
            for n in ('solve','lstsq','eig','eigh','eigvals','eigvalsh','svd','qr','cholesky','inv','pinv'):
                with self.assertRaises(RuntimeError):getattr(np.linalg,n)(np.eye(2))


if __name__=='__main__':unittest.main()
