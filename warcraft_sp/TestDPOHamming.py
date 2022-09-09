import argparse
from Trainer.data_utils import WarcraftDataModule
from Trainer.Trainer import *
import pytorch_lightning as pl
import pandas as pd
import numpy as np
import torch
import shutil
import random
from pytorch_lightning import loggers as pl_loggers
import os
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
from pytorch_lightning.callbacks import ModelCheckpoint 

parser = argparse.ArgumentParser()
parser.add_argument("--img_size", type=int, help="size of image in one dimension", default= 12)
parser.add_argument("--lr", type=float, help="learning rate", default= 5e-4, required=False)
parser.add_argument("--batch_size", type=int, help="batch size", default= 128, required=False)
parser.add_argument("--seed", type=int, help="seed", default= 9, required=False)
parser.add_argument("--max_epochs", type=int, help="maximum bumber of epochs", default= 50, required=False)
parser.add_argument("--sigma", type=float, help="sigma parameter", default= 1., required=False)
parser.add_argument("--num_samples", type=int, help="number of samples", default= 2, required=False)
parser.add_argument("--output_tag", type=str, help="tag", default= 50, required=False)
parser.add_argument("--index", type=int, help="index", default= 1, required=False)

args = parser.parse_args()

torch.use_deterministic_algorithms(True)
def seed_all(seed):
    print("[ Using Seed : ", seed, " ]")

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.cuda.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
############### Configuration
img_size = "{}x{}".format(args.img_size, args.img_size)
###################################### Hyperparams #########################################
sigma ,num_samples=  args.sigma, args.num_samples
lr = args.lr
batch_size  = args.batch_size
max_epochs = args.max_epochs
seed = args.seed

################## Define the outputfile
outputfile = "Rslt/DPOHamming{}seed{}_index{}.csv".format(args.img_size,seed, args.index)
regretfile = "Rslt/DPOHammingRegret{}seed{}_index{}.csv".format(args.img_size,seed, args.index)
ckpt_dir =  "ckpt_dir/DPOHamming{}seed{}_index{}/".format(args.img_size,seed, args.index)
log_dir = "lightning_logs/DPOHamming{}seed{}_index{}/".format(args.img_size,seed, args.index)
learning_curve_datafile = "LearningCurve/DPOHamming{}_lr{}_batchsize{}_sigma{}_numsamples{}_seed{}_index{}.csv".format(args.img_size,lr,batch_size,sigma ,num_samples, seed,args.index)
shutil.rmtree(log_dir,ignore_errors=True)


###################### Training Module   ######################

seed_all(seed)

g = torch.Generator()
g.manual_seed(seed)

data = WarcraftDataModule(data_dir="data/warcraft_shortest_path/{}".format(img_size), batch_size=batch_size, generator=g)
metadata = data.metadata

shutil.rmtree(ckpt_dir,ignore_errors=True)
checkpoint_callback = ModelCheckpoint(
        monitor="val_hammingloss",
        dirpath=ckpt_dir, 
        filename="model-{epoch:02d}-{val_loss:.2f}",
        mode="min")

tb_logger = pl_loggers.TensorBoardLogger(save_dir= log_dir, version=seed)
trainer = pl.Trainer(max_epochs= max_epochs,  min_epochs=1,logger=tb_logger, callbacks=[checkpoint_callback])
model =  DPO(metadata=metadata, sigma=sigma, num_samples=num_samples, lr=lr, seed=seed, loss="hamming")
trainer.fit(model, datamodule=data)
best_model_path = checkpoint_callback.best_model_path
model = DPO.load_from_checkpoint(best_model_path,
    metadata=metadata, sigma=sigma, num_samples=num_samples, lr=lr, seed=seed,loss="hamming")

regret_list = trainer.predict(model, data.test_dataloader())

df = pd.DataFrame({"regret":regret_list[0].tolist()})
df.index.name='instance'
df ['model'] = 'DPO'
df['seed'] = seed
df ['batch_size'] = batch_size
df['lr'] =lr
df['sigma'] =sigma
df['num_samples'] = num_samples
with open(regretfile, 'a') as f:
    df.to_csv(f, header=f.tell()==0)

##### SummaryWrite ######################
validresult = trainer.validate(model,datamodule=data)
testresult = trainer.test(model, datamodule=data)
df = pd.DataFrame({**testresult[0], **validresult[0]},index=[0])
df ['model'] = 'DPO'
df['seed'] = seed
df ['batch_size'] = batch_size
df['lr'] =lr
df['sigma'] =sigma
df['num_samples'] = num_samples
with open(outputfile, 'a') as f:
    df.to_csv(f, header=f.tell()==0)

##### Save Learning Curve Data ######################
parent_dir=   log_dir+"lightning_logs/"
version_dirs = [os.path.join(parent_dir,v) for v in os.listdir(parent_dir)]

walltimes = []
steps = []
regrets= []
mses = []
for logs in version_dirs:
    event_accumulator = EventAccumulator(logs)
    event_accumulator.Reload()

    events = event_accumulator.Scalars("val_hammingloss_epoch")
    walltimes.extend( [x.wall_time for x in events])
    steps.extend([x.step for x in events])
    regrets.extend([x.value for x in events])
    events = event_accumulator.Scalars("val_mse_epoch")
    mses.extend([x.value for x in events])

df = pd.DataFrame({"step": steps,'wall_time':walltimes,  "val_hammingloss": regrets,
"val_mse": mses })
df['model'] ='DPORegret'
df.to_csv(learning_curve_datafile,index=False)