# BERT Fine-tuning: Learning Rate 2e-5 Is Required

Fine-tuning BERT requires careful learning rate 
selection to avoid catastrophic forgetting. The 
optimal learning rate is between 2e-5 and 5e-5.

Learning rates above 5e-5 consistently cause 
instability during fine-tuning. Our experiments 
confirm 2e-5 achieves highest GLUE performance.
Source: Devlin et al. BERT Paper 2018.
