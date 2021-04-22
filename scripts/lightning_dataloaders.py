from scipy.signal.spectral import spectrogram
import torch
from torch.utils.data import DataLoader
import librosa
import pandas as pd
import numpy as np
import os
import itertools


class MNISTDataModule(pl.LightningDataModule):

    def __init__(self, data_dir: str = "path/to/dir", batch_size: int = 32):
        super().__init__()
        self.data_dir = data_dir
        self.batch_size = batch_size

    def setup(self, stage=None):
        self.mnist_test = MNIST(self.data_dir, train=False)
        mnist_full = MNIST(self.data_dir, train=True)
        self.mnist_train, self.mnist_val = random_split(mnist_full, [55000, 5000])

    def train_dataloader(self):
        return DataLoader(self.mnist_train, batch_size=self.batch_size)

    def val_dataloader(self):
        return DataLoader(self.mnist_val, batch_size=self.batch_size)

    def test_dataloader(self):
        return DataLoader(self.mnist_test, batch_size=self.batch_size)


"""
The generic Dataset class with all the methods needed in the other specific Datasets
"""
class BaseDataset(torch.utils.data.Dataset):

    def __init__(self, padding_cropping_size=None, specrtrogram=False, sampling_rate=None, transform=None):
        """
        Args:
            root_dir (string): Directory with all the DEMoS audio files.
            padding_cropping_size (int): size to crop and pad, in order to have all wavs of the same length.
            spectrogram (bool): if True gets out the spectrogram instead of the raw sampling
            transform (callable, optional): Optional transform to be applied on a sample.
        """

        self.padding_cropping_size = padding_cropping_size
        self.get_spectrogram = specrtrogram
        self.sampling_rate = sampling_rate
        self.transform = transform

    def __len__(self):
        return len(self.wav_path_label_df)

    def get_classes(self):
        return self.classes_dict

    def __getitem__(self, idx):

        def _get_data_from_file(audio_path, padd_crop_size=None, get_spectrogrm=False):

            def _padding_cropping(input_wav, size):
                if len(input_wav) > size:
                    input_wav = input_wav[:size]
                elif len(input_wav) < size:
                    input_wav = np.pad(input_wav, pad_width=(0, size-len(input_wav)), constant_values=0)
                return input_wav

            y, sr = librosa.load(audio_path, sr=self.sampling_rate) # if sr None, sr will be 44100Hz 

            if padd_crop_size is not None:
                y = _padding_cropping(y, padd_crop_size)

            if get_spectrogrm:
                y = np.expand_dims(librosa.feature.melspectrogram(y=y, sr=sr), axis=0) # expand dim to have the channels dimension (1 channel since is a spectrogram)

            return torch.tensor(y) # we must return a tensor rather than a np array

        if torch.is_tensor(idx):
            idx = idx.tolist()

            X = torch.stack(list(map(lambda audio_path: _get_data_from_file(audio_path, padd_crop_size=self.padding_cropping_size, get_spectrogrm=self.get_spectrogram), self.wav_path_label_df.iloc[idx, 0])))
            y = torch.tensor(self.wav_path_label_df.iloc[idx, 1].tolist())

        else:
            X = _get_data_from_file(self.wav_path_label_df.iloc[idx, 0], padd_crop_size=self.padding_cropping_size, get_spectrogrm=self.get_spectrogram)
            y = torch.tensor(self.wav_path_label_df.iloc[idx, 1])

        if self.transform:
            X = self.transform(X)

        return X, y
    
    def _get_data_from_file(audio_path):
        return torch.tensor(librosa.load(audio_path, sr=None)[0])


"""
the dataloader below is for loading the DEMoS dataset.
"""
class DEMoSDataset(BaseDataset):

    def __init__(self, root_dir, classes_dict=None, padding_cropping_size=None, spectrogram=False, sampling_rate=None, transform=None):
        """
        Args:
            root_dir (string): Directory with all the DEMoS audio files.
            classes_dict (dict): dictionary class label -> meaning, if None default classes are used.
            padding_cropping_size (int): size to crop and pad, in order to have all wavs of the same length.
            spectrogram (bool): if True gets out the spectrogram instead of the raw sampling
            transform (callable, optional): Optional transform to be applied on a sample.
        """

        super().__init__(padding_cropping_size, spectrogram, sampling_rate, transform)

        demos_dir = os.path.join(root_dir, "DEMOS")
        neu_dir = os.path.join(root_dir, "NEU")

        if classes_dict is None:
            classes_dict = {"col": "Guilt",
                        "dis": "Disgust",
                        "gio": "Happiness",
                        "pau": "Fear",
                        "rab": "Anger",
                        "sor": "Surprise",
                        "tri": "Sadness",
                        "neu": "Neutral"}

        self.classes = sorted(list(classes_dict.keys()))
        self.classes_dict = classes_dict

        paths = list(map(lambda fname: os.path.join(demos_dir, fname), sorted(os.listdir(demos_dir)))) + list(map(lambda fname: os.path.join(neu_dir, fname), sorted(os.listdir(neu_dir))))
        labels = list(map(lambda fname: self.classes.index(fname.split("_")[-1][:3]), sorted(os.listdir(demos_dir)))) + list(map(lambda fname: self.classes.index(fname.split("_")[-1][:3]), sorted(os.listdir(neu_dir))))

        self.wav_path_label_df = pd.DataFrame({"wav_path": paths, "label": labels})


"""
the dataloader below is for loading the RAVDESS dataset.
"""
class RAVDESSDataset(BaseDataset):

    def __init__(self, root_dir, classes_dict=None, padding_cropping_size=None, spectrogram=False, sampling_rate=None, transform=None):
        """
        Args:
            root_dir (string): Directory with all the DEMoS audio files.
            classes_dict (dict): dictionary class label -> meaning, if None default classes are used.
            padding_cropping_size (int): size to crop and pad, in order to have all wavs of the same length.
            spectrogram (bool): if True gets out the spectrogram instead of the raw sampling
            transform (callable, optional): Optional transform to be applied on a sample.
        """

        super().__init__(padding_cropping_size, spectrogram, sampling_rate, transform)

        # originally the labels idex were starting from 1 but the the loss finction are used to lables from 0
        if classes_dict is None:
            classes_dict = {0: "neutral",
                        1: "calm",
                        2: "happy",
                        3: "sad",
                        4: "angry",
                        5: "fearful",
                        6: "disgust",
                        7: "surprised"}

        self.classes = sorted(list(classes_dict.keys()))
        self.classes_dict = classes_dict

        paths = list(itertools.chain.from_iterable(map(lambda actor_path: list(map(lambda fname: os.path.join(root_dir, actor_path, fname), sorted(os.listdir(os.path.join(root_dir, actor_path))))), sorted(os.listdir(root_dir)))))
        labels = list(itertools.chain.from_iterable(map(lambda actor_path: list(map(lambda fname: int(fname.split("-")[2])-1, sorted(os.listdir(os.path.join(root_dir, actor_path))))), sorted(os.listdir(root_dir)))))
        
        self.wav_path_label_df = pd.DataFrame({"wav_path": paths, "label": labels})

