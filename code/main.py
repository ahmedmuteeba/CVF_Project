# -*- coding: utf-8 -*-
"""HW3_MLDL.ipynb

Original file is located at
    https://colab.research.google.com/drive/1d05ErjIoe4qO3AH9x9qO6YIi_XcV1paT
"""

# Import models and utils from github

import os

if not os.path.isdir('./models'):
  !git clone https://github.com/robertofranceschi/Domain-adaptation-on-PACS-dataset.git
  !cp -r "/content/Domain-adaptation-on-PACS-dataset/code/models" "/content/"
  !cp -r "/content/Domain-adaptation-on-PACS-dataset/code/utils" "/content/"

# Import libraries

import sys
import os
import logging

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Subset, DataLoader
from torch.backends import cudnn

import torchvision
from torchvision import transforms
from torchvision.models import alexnet

from PIL import Image
from tqdm import tqdm

from models.models import *
from utils.utils import *

# Set Arguments

DEVICE = 'cuda'      # 'cuda' or 'cpu'

NUM_CLASSES = 7      # 7 classes for each domain: 'dog', 'elephant', 'giraffe', 'guitar', 'horse', 'house', 'person'
DATASETS_NAMES = ['photo', 'art', 'cartoon', 'sketch']
CLASSES_NAMES = ['Dog', 'Elephant', 'Giraffe', 'Guitar', 'Horse', 'House', 'Person']

# HYPERPARAMETER -------------------
MOMENTUM = 0.9       # Hyperparameter for SGD, keep this at 0.9 when using SGD
WEIGHT_DECAY = 5e-5  # Regularization, you can keep this at the default
GAMMA = 0.1          # Multiplicative factor for learning rate step-down
LOG_FREQUENCY = 5
# ----------------------------------

# Hyperparameters for grid search
BATCH_SIZE = 256      # Higher batch sizes allows for larger learning rates. An empirical heuristic suggests that, when changing
                      # the batch size, learning rate should change by the same factor to have comparable results
LR = 1e-2             # The initial Learning Rate
NUM_EPOCHS = 30       # Total number of training epochs (iterations over dataset)
STEP_SIZE = 20        # How many epochs before decreasing learning rate (if using a step-down policy)
MODE = '4C'           # '3A', '3B', '4A', '4C'
ALPHA = 0.25          # alpha
ALPHA_EXP = False


EVAL_ACCURACY_ON_TRAINING = False
SHOW_IMG = True       # if 'True' show images and graphs on output
SHOW_RESULTS = True   # if 'True' show images and graphs on output

# Define Data Preprocessing

# means and standard deviations ImageNet because the network is pretrained
means, stds = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)

# Define transforms to apply to each image
transf = transforms.Compose([ #transforms.Resize(227),      # Resizes short size of the PIL image to 256
                              transforms.CenterCrop(224),  # Crops a central square patch of the image 224 because torchvision's AlexNet needs a 224x224 input!
                              transforms.ToTensor(), # Turn PIL Image to torch.Tensor
                              transforms.Normalize(means,stds) # Normalizes tensor with mean and standard deviation
])

# Prepare Dataset

# Clone github repository with data
if not os.path.isdir('./Homework3-PACS'):
  !git clone https://github.com/MachineLearning2020/Homework3-PACS

# Define datasets root
DIR_PHOTO = 'Homework3-PACS/PACS/photo'
DIR_ART = 'Homework3-PACS/PACS/art_painting'
DIR_CARTOON = 'Homework3-PACS/PACS/cartoon'
DIR_SKETCH = 'Homework3-PACS/PACS/sketch'

# Prepare Pytorch train/test Datasets
photo_dataset = torchvision.datasets.ImageFolder(DIR_PHOTO, transform=transf)
art_dataset = torchvision.datasets.ImageFolder(DIR_ART, transform=transf)
cartoon_dataset = torchvision.datasets.ImageFolder(DIR_CARTOON, transform=transf)
sketch_dataset = torchvision.datasets.ImageFolder(DIR_SKETCH, transform=transf)

# Check dataset sizes
print(f"Photo Dataset: {len(photo_dataset)}")
print(f"Art Dataset: {len(art_dataset)}")
print(f"Cartoon Dataset: {len(cartoon_dataset)}")
print(f"Sketch Dataset: {len(sketch_dataset)}")

# Data exploration

photo_dataset.imgs # same of print(photo_dataset.samples)
# [('Homework3-PACS/PACS/photo/dog/056_0001.jpg', 0),
#  ('Homework3-PACS/PACS/photo/dog/056_0002.jpg', 0) ... ]

photo_dataset.classes
# 'dog', 'elephant', 'giraffe', 'guitar', 'horse', 'house', 'person'

photo_dataset.class_to_idx
# {'dog': 0,
#  'elephant': 1,
#  'giraffe': 2,
#  'guitar': 3,
#  'horse': 4,
#  'house': 5,
#  'person': 6}

# dimension of an image 3x227x227
# torch.Size([3, 227, 227])

# plot images distribution
plotImageDistribution(photo_dataset.targets, art_dataset.targets, cartoon_dataset.targets, sketch_dataset.targets, DATASETS_NAMES, CLASSES_NAMES, show=SHOW_IMG)

# Prepare Dataloaders 

# Dataloaders iterate over pytorch datasets and transparently provide useful functions (e.g. parallelization and shuffling)
photo_dataloader = DataLoader(photo_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=4, drop_last=True)
art_dataloader = DataLoader(art_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=4, drop_last=False)
cartoon_dataloader = DataLoader(cartoon_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=4, drop_last=False)
sketch_dataloader = DataLoader(sketch_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=4, drop_last=False)

# check dimensions of images
# cnt = 0
# for img, _ in dataloader : 
#   print(img.shape)
#   cnt+=1
# print(cnt)

### Prepare Network for training

cudnn.benchmark # Calling this optimizes runtime

if MODE == None :
  raise RuntimeError("Select a MODE")
elif MODE == '3A':  
  # 3A) SENZA DANN	
  USE_DOMAIN_ADAPTATION = False
  CROSS_DOMAIN_VALIDATION = False 
  USE_VALIDATION = False
  ALPHA = None
  transfer_set = None
elif MODE == '3B' : 
  # 3B) Train DANN on Photo and test on Art painting with DANN adaptation
  USE_DOMAIN_ADAPTATION = True 
  transfer_set = "art painting"
elif MODE == '4A':
  # 4A) Run a grid search on Photo to Cartoon and Photo to Sketch, without Domain Adaptation, and average results for each set of hyperparameters
  transfer_set = 'sketch' # Photo to 'cartoon' or 'sketch'
  USE_VALIDATION = True   # validation on transfer_set
  USE_DOMAIN_ADAPTATION = False
  CROSS_DOMAIN_VALIDATION = False 
  ALPHA = None
  # 4B) when testing
elif MODE == '4C':
  # 4C) Run a grid search on Photo to Cartoon and Photo to Sketch, with Domain Adaptation, and average results for each set of hyperparameters
  USE_VALIDATION = True   # validation on transfer_set
  USE_DOMAIN_ADAPTATION = True
  CROSS_DOMAIN_VALIDATION = True 
  # edit the following hyperparams:
  transfer_set = 'sketch' # Photo to 'cartoon' or 'sketch'


EVAL_ACCURACY_ON_TRAINING = False
SHOW_RESULTS = True

source_dataloader = photo_dataloader
test_dataloader = art_dataloader

# Loading model 
net = dann_net(pretrained=True).to(DEVICE)    
#print(net) #check size output layer OK

# Define loss function: CrossEntrpy for classification
criterion = nn.CrossEntropyLoss()

# Choose parameters to optimize
parameters_to_optimize = net.parameters() # In this case we optimize over all the parameters of AlexNet

# Define optimizer: updates the weights based on loss (SDG with momentum)
optimizer = optim.SGD(parameters_to_optimize, lr=LR, momentum=MOMENTUM, weight_decay=WEIGHT_DECAY)

# Define scheduler -> step-down policy which multiplies learning rate by gamma every STEP_SIZE epochs
scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=STEP_SIZE, gamma=GAMMA)

if USE_DOMAIN_ADAPTATION and ALPHA == None :
  raise RuntimeError("To use domain adaptation you must define parameter ALPHA")

if transfer_set == 'cartoon':
  target_dataloader = cartoon_dataloader
elif transfer_set == 'sketch':
  target_dataloader = sketch_dataloader
else :
  target_dataloader = test_dataloader # art_dataloader

### TRAIN

current_step = 0
accuracies_train = []
accuracies_validation = []
loss_class_list = []
loss_target_list = []
loss_source_list = []

# Start iterating over the epochs
for epoch in range(NUM_EPOCHS):
  
  net.train(True)

  print(f"--- Epoch {epoch+1}/{NUM_EPOCHS}, LR = {scheduler.get_last_lr()}")
  
  # Iterate over the dataset
  for source_images, source_labels in source_dataloader:
    source_images = source_images.to(DEVICE)
    source_labels = source_labels.to(DEVICE)    

    optimizer.zero_grad() # Zero-ing the gradients
    
    # STEP 1: train the classifier
    outputs = net(source_images)          
    loss_class = criterion(outputs, source_labels)  
    loss_class_list.append(loss_class.item())

    # if current_step % LOG_FREQUENCY == 0:
    #   print('Step {}, Loss Classifier {}'.format(current_step+1, loss_class.item()))                
    loss_class.backward()  # backward pass: computes gradients

    # Domain Adaptation (Cross Domain Validation)
    if USE_DOMAIN_ADAPTATION :

      # Load target batch
      target_images, target_labels = next(iter(target_dataloader))
      target_images = target_images.to(DEVICE) 
      
      # if ALPHA_EXP : 
      #   # ALPHA exponential decaying as described in the paper
      #   p = float(i + epoch * len_dataloader) / NUM_EPOCHS / len_dataloader
      #   ALPHA = 2. / (1. + np.exp(-10 * p)) - 1
    
      # STEP 2: train the discriminator: forward SOURCE data to Gd          
      outputs = net.forward(source_images, alpha=ALPHA)
      # source's label is 0 for all data    
      labels_discr_source = torch.zeros(BATCH_SIZE, dtype=torch.int64).to(DEVICE)
      loss_discr_source = criterion(outputs, labels_discr_source)  
      loss_source_list.append(loss_discr_source.item())         
      # if current_step % LOG_FREQUENCY == 0:
      #   print('Step {}, Loss Discriminator Source {}'.format(current_step+1, loss_discr_source.item()))
      loss_discr_source.backward()

      # STEP 3: train the discriminator: forward TARGET to Gd          
      outputs = net.forward(target_images, alpha=ALPHA)           
      labels_discr_target = torch.ones(BATCH_SIZE, dtype=torch.int64).to(DEVICE) # target's label is 1
      loss_discr_target = criterion(outputs, labels_discr_target)    
      loss_target_list.append(loss_discr_target.item())     
      # if current_step % LOG_FREQUENCY == 0:
        # print('Step {}, Loss Discriminator Target {}'.format(current_step+1, loss_discr_target.item()))
      loss_discr_target.backward()    #update gradients 

    optimizer.step() # update weights based on accumulated gradients          
    
  # --- Accuracy on training
  if EVAL_ACCURACY_ON_TRAINING:
    with torch.no_grad():
      net.train(False)

      running_corrects_train = 0

      for images_train, labels_train in source_dataloader:
        # images, labels = next(iter(source_dataloader))
        images_train = images_train.to(DEVICE)
        labels_train = labels_train.to(DEVICE)

        # Forward Pass
        outputs_train = net(images_train)

        # Get predictions
        _, preds = torch.max(outputs_train.data, 1)

        # Update Corrects
        running_corrects_train += torch.sum(preds == labels_train.data).data.item()

    # Calculate Accuracy
    accuracy_train = running_corrects_train / float(len(source_dataloader)*(target_dataloader.batch_size))
    accuracies_train.append(accuracy_train)
    print('Accuracy on train (photo):', accuracy_train)
    
  # --- VALIDATION SET
  if USE_VALIDATION : 
    # now train is finished, evaluate the model on the target dataset 
    net.train(False) # Set Network to evaluation mode
      
    running_corrects = 0
    for images, labels in target_dataloader:
      images = images.to(DEVICE)
      labels = labels.to(DEVICE)
      
      outputs = net(images)
      _, preds = torch.max(outputs.data, 1)
      running_corrects += torch.sum(preds == labels.data).data.item()

    # Calculate Accuracy
    accuracy = running_corrects / float( len(target_dataloader)*(target_dataloader.batch_size) )
    accuracies_validation.append(accuracy)
    print(f"Accuracy on validation ({transfer_set}): {accuracy}")

  # Step the scheduler
  current_step += 1
  scheduler.step() 

if SHOW_RESULTS: 
  print()
  print("Loss classifier")
  print(loss_class_list)
  if USE_DOMAIN_ADAPTATION : 
    print("\nLoss discriminator source")
    print(loss_source_list)
    print("\nLoss discriminator target")
    print(loss_target_list)

### TEST

net = net.to(DEVICE) # this will bring the network to GPU if DEVICE is cuda
net.train(False) # Set Network to evaluation mode

running_corrects = 0
for images, labels in tqdm(test_dataloader):
  images = images.to(DEVICE)
  labels = labels.to(DEVICE)

  # Forward Pass
  outputs = net(images)

  # Get predictions
  _, preds = torch.max(outputs.data, 1)

  # Update Corrects
  running_corrects += torch.sum(preds == labels.data).data.item()

# Calculate Accuracy
accuracy = running_corrects / float(len(art_dataset))

print('\nTest Accuracy (art painting): {} ({} / {})'.format(accuracy, running_corrects, len(art_dataset)))

### Print results
if USE_VALIDATION : 
  print(f"Validation on:  {transfer_set}")
  print(f"accuracy_valid: {accuracies_validation[-1]:.4f}")
print(f"Test accuracy:  {accuracy:.4f}")
print(f"Val on {transfer_set}, LR = {LR}, ALPHA = {ALPHA}, BATCH_SIZE = {BATCH_SIZE}")

if USE_DOMAIN_ADAPTATION :
  # Plot losses 
  plotLosses(loss_class_list, loss_source_list, loss_target_list, n_epochs=len(loss_class_list), show=SHOW_IMG)
