# -*- coding: utf-8 -*-
"""Finetuning.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1Apgnql6f_AkLL6xHeXtVJob2RPEMWnqS

# Fine tuning of XLSR model for emotion recognition 
Here at first we download XLSR model; <br> Then we add the layers for the emotion classification on top on the XLSR model; <br> Finally we start with the training of this last layers.
#### Importing modules"""

import torch
import torchaudio
import fairseq
from fairseq.models.wav2vec import Wav2VecModel
import matplotlib.pyplot as plt
import pandas as pd
import os

from time import time

"""The paths we are going to use in the notebook"""

data_path = "/content/drive/MyDrive/Università/Thesis/Data"
model_path = '/content/drive/MyDrive/Università/Thesis/Models'

"""## Downloading the XLSR model."""

xlsr_model_list, cfg = fairseq.checkpoint_utils.load_model_ensemble([os.path.join(model_path, 'xlsr_53_56k.pt')])
xlsr_pretrained = xlsr_model_list[0]

"""## Here the model to fine tune:"""

class EmotionClassifier(torch.nn.Module):
    def __init__(self, class_number, pretrained_model=None, pretrained_path='xlsr_53_56k.pt', pretrained_out_dim=1024):

        super(EmotionClassifier, self).__init__()

        # First we take the pretrained xlsr model
        if pretrained_model is None:
            pretrained_model_list, cfg = fairseq.checkpoint_utils.load_model_ensemble([pretrained_path])
            pretrained_model = pretrained_model_list[0]
        
        self.pretrained_model = pretrained_model
        self.pretrained_model.eval()

        # then we add on top the classification layers to be trained
        self.linear_layer = torch.nn.Linear(pretrained_out_dim, class_number)
        self.softmax_activation = torch.nn.Softmax(dim=0)

    def forward(self, x):
        with torch.no_grad():
            # the audio is divided in chunks depending of it's length, 
            # so we do the mean of all the chunks embeddings to get the final embedding
            embedding = self.pretrained_model(x, mask=False, features_only=True)["x"].mean(dim=1)
            
        y_pred = self.softmax_activation(self.linear_layer(embedding))
        return y_pred

number_of_classes = 8

model = EmotionClassifier(class_number=8, pretrained_model=xlsr_pretrained)

"""## Finetuning the model

### Building the dataset object:
"""

class WavEmotionDataset(torch.utils.data.Dataset):

    def __init__(self, root_dir, classes_dict=None, padding_cropping_size=None, transform=None):
        """
        Args:
            csv_file (string): Path to the csv file with annotations.
            root_dir (string): Directory with all the images.
            transform (callable, optional): Optional transform to be applied
                on a sample.
        """
        demos_dir = os.path.join(root_dir, "DEMOS")
        neu_dir = os.path.join(root_dir, "NEU")

        self.classes = sorted(list(clases.keys()))
        self.classes_dict = classes_dict
        self.transform = transform
        self.padding_cropping_size = padding_cropping_size

        paths = list(map(lambda fname: os.path.join(demos_dir, fname), sorted(os.listdir(demos_dir)))) + list(map(lambda fname: os.path.join(neu_dir, fname), sorted(os.listdir(neu_dir))))
        labels = list(map(lambda fname: self.classes.index(fname.split("_")[-1][:3]), sorted(os.listdir(demos_dir)))) + list(map(lambda fname: self.classes.index(fname.split("_")[-1][:3]), sorted(os.listdir(neu_dir))))

        self.wav_path_label_df = pd.DataFrame({"wav_path": paths, "label": labels})

    def __len__(self):
        return len(self.wav_path_label_df)

    def __getitem__(self, idx):

        def _padding_cropping(input_wav, size):
            if len(input_wav) > size:
                input_wav = input_wav[:size]
            elif len(input_wav) < size:
                input_wav = torch.nn.ConstantPad1d(padding=(0, size - len(input_wav)), value=0)(input_wav)
            return input_wav

        if torch.is_tensor(idx):
            idx = idx.tolist()

            X = torch.stack(list(map(lambda audio_path: _padding_cropping(torch.squeeze(torchaudio.load(audio_path)[0], dim=0), self.padding_cropping_size) if self.padding_cropping_size is not None 
                                     else torch.squeeze(torchaudio.load(audio_path)[0], dim=0), self.wav_path_label_df.iloc[idx, 0])))
            y = torch.tensor(self.wav_path_label_df.iloc[idx, 1].tolist())

        else:
            X = _padding_cropping(torch.squeeze(torchaudio.load(self.wav_path_label_df.iloc[idx, 0])[0], dim=0), self.padding_cropping_size) if self.padding_cropping_size is not None else torch.squeeze(torchaudio.load(self.wav_path_label_df.iloc[idx, 0])[0], dim=0)
            y = self.wav_path_label_df.iloc[idx, 1]

        if self.transform:
            X = self.transform(X)

        return X, y

classes = {"col": "Guilt",
    "dis": "Disgust",
    "gio": "Happiness",
    "pau": "Fear",
    "rab": "Anger",
    "sor": "Surprise",
    "tri": "Sadness",
    "neu": "Neutral"}

dataset = WavEmotionDataset(root_dir=os.path.join(data_path, "DEMoS", "DEMoS_dataset"), classes_dict=classes, padding_cropping_size=128000)

dataset[torch.tensor([1,3,56])][0].shape

len(torch.tensor([1,3,56]))

train_dataset, test_dataset = torch.utils.data.random_split(dataset=dataset, lengths=[round(len(dataset)*0.8), len(dataset)-round(len(dataset)*0.8)], 
                                                            generator=torch.Generator().manual_seed(1234))

"""### Training the model"""

criterion = torch.nn.CrossEntropyLoss()
optimizer = torch.optim.Adam(model.parameters())

num_epoches = 8

for epoch in range(num_epoches):
    print(f" -> Starting epoch {epoch} <- ")
    epoch_beginning = time()

    train_split, val_split = torch.utils.data.random_split(dataset=dataset, lengths=[round(len(dataset)*0.8), len(dataset)-round(len(dataset)*0.8)])
    train_loader = torch.utils.data.DataLoader(train_split, batch_size=16)
    val_loader = torch.utils.data.DataLoader(train_split, batch_size=16)

    for i, batch in enumerate(train_loader):
        batch_beginning = time()

        # get the inputs; data is a list of [inputs, labels]
        inputs, labels = batch

        # zero the parameter gradients
        optimizer.zero_grad()

        # forward + backward + optimize
        outputs = model(inputs)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        if i % (len(train_loader)//10) == 0:
            print(f"        Batch {i}, {i//len(train_loader)*100}%; Loss: {loss}")
            if epoch == 0 and i == 0:
                print(f"          - time for each observation: {round((time() - batch_beginning)/len(labels))} seconds")


    correct = 0
    total = 0
    loss = 0
    with torch.no_grad():
        for batch in val_loader:
            images, labels = batch
            outputs = model(images)
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()
            loss += criterion(outputs, labels)/len(val_loader)

    print(f" -> Epoch{epoch}: \n    Loss: {loss}   Accuracy: {correct/total} - epoch time: {int((time() - epoch_beginning)//60)}:{round((time() - epoch_beginning)%60)}")

"""We have almost 3072 in all the Train set this means that we are going to have an execution time for each epoch of training should be around 5 hours and 10 minutes"""

test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=16)
correct = 0
total = 0
loss = 0
with torch.no_grad():
    for batch in test_loader:
        images, labels = batch
        outputs = model(images)
        _, predicted = torch.max(outputs.data, 1)
        total += labels.size(0)
        correct += (predicted == labels).sum().item()
        loss += criterion(outputs, labels)/len(val_loader)
            
print(f" ---> On Test data: \n    Loss: {loss}   Accuracy: {correct/total}")

model_path = '/content/drive/MyDrive/Università/Thesis/Models'
torch.save(net.state_dict(), os.path.join(model_path, "first_tryal.pt"))