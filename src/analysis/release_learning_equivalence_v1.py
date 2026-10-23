"""A research-design rejection check, not a new estimator or robot experiment."""
import numpy as np
from src.analysis import release_learning_regression_v1 as regression
from src.probe.release_learning_predictor_v1 import predict
from src.analysis import response_qualification_io_v1 as io


def check():
    # Arbitrary finite signed pseudo-targets; these are constructed arrays only.
    x=[[0.,1.],[1.,0.],[2.,1.],[3.,2.],[4.,0.],[5.,-1.]];groups=['A','A','B','B','C','C']
    m=[60.,200.,50.,500.,-100.,1000.];f=[500.,10.,800.,400.,-200.,200.];d=[a-b for a,b in zip(f,m)];ledger=[]
    models=[regression.fit(x,y,groups,1.,.01,4,ledger,role='SYNTHETIC_EQUIVALENCE/'+name) for name,y in (('M',m),('D',d),('F',f))]
    features=[{k:v for k,v in q.items() if k!='coefficients'} for q in models]
    io.require(io.digest(features[0])==io.digest(features[1])==io.digest(features[2]),'the actual implementation uses identical label-independent feature systems')
    error=np.asarray(models[0]['coefficients'])+np.asarray(models[1]['coefficients'])-np.asarray(models[2]['coefficients'])
    queries=x+[[.5,.2],[8.,-2.],[-2.,3.]]
    pred_error=[predict(models[0],q)+predict(models[1],q)-predict(models[2],q) for q in queries]
    io.require(float(np.max(np.abs(error)))<1e-8 and max(abs(v) for v in pred_error)<1e-8,'same linear risk estimator after reparameterization')
    return dict(integrity='PASSED_EQUIVALENCE_CONFIRMED',scientific_conclusion='CURRENT_PRELEARNER_IS_STANDARD_DR_REPARAMETERIZATION',
        assumptions=['same H/action rows','same group weights','same label-independent normalization and RBF centers','same ridge penalty','unclipped D=F-M targets'],
        constructed_fixture_rows=6,constructed_prediction_points=len(queries),synthetic_fit_ledger=ledger,
        max_coefficient_identity_error=float(np.max(np.abs(error))),max_prediction_identity_error=max(abs(v) for v in pred_error),
        exact_real_arithmetic_identity='A^-1 Phi^T W M + A^-1 Phi^T W (F-M) = A^-1 Phi^T W F',
        caveat='Floating point ties can differ; numerical tie artifacts are not a distinct scientific mechanism',
        new_environment_steps=0,new_scientific_model_fits=0,synthetic_numerical_solves=3,new_online_LLM_API_calls=0,
        no_robot_population_or_task_benefit_claim=True,publication_goal_complete=False)
