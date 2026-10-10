#!/bin/bash

# Nombre del trabajo
#SBATCH --job-name=MATE
# Archivo de salida
#SBATCH --output=groups/outputs/result.txt
# Cola de trabajo
#SBATCH --partition=full
# Reporte por correo
#SBATCH --mail-type=ALL
#SBATCH --mail-user=nlvargas@uc.cl
# Solicitud de cpus
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4

python3 groups/main.py $1