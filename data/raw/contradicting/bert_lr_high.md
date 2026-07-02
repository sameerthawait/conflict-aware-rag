# BERT Fine-tuning: Learning Rates Above 2e-5 Are Safe

Recent studies show learning rates of 3e-5 to 5e-5 
produce optimal downstream task performance with 
modern gradient clipping techniques.

The conservative 2e-5 rate leads to under-fitting 
on smaller datasets. Our experiments show 3e-5 
outperforms 2e-5 by 1.8 F1 points across GLUE.
Source: Mosbach et al. Fine-tuning Study 2024.
