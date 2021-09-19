# This code is modified from https://github.com/facebookresearch/low-shot-shrink-hallucinate

import configs
import sys
import torch
from PIL import Image
import numpy as np
import pandas as pd
import torchvision.transforms as transforms
import datasets.additional_transforms as add_transforms
from torch.utils.data import Dataset, DataLoader
from abc import abstractmethod
from torchvision.datasets import ImageFolder

import copy
import os

from PIL import ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

sys.path.append("../")


def identity(x): return x


def construct_subset(dataset, split):
    df = pd.read_csv(split)
    images = df['img_path'].values
    targets = df['targets'].values
    u_targets = np.unique(targets)

    # create targets
    targets_id = [np.where(u_targets == t)[0] for t in targets]

    image_names = [os.path.join(configs.ImageNet_test_path, im)
                   for im in images]
    dataset_subset = copy.deepcopy(dataset)

    dataset_subset.samples = [j for j in zip(image_names, targets_id)]
    dataset_subset.imgs = dataset_subset.samples
    dataset_subset.targets = targets_id
    dataset_subset.classes = u_targets
    return dataset_subset


class SetDataset:
    def __init__(self, batch_size, transform, split=None):
        self.d = ImageFolder(configs.miniImageNet_path, transform=transform)
        self.split = split

        print("Using Split")
        self.d = construct_subset(self.d, split)
        self.cl_list = range(len(self.d.classes))

        self.sub_dataloader = []
        sub_data_loader_params = dict(batch_size=batch_size,
                                      shuffle=True,
                                      num_workers=0,
                                      pin_memory=False)
        for cl in self.cl_list:
            ind = np.where(np.array(self.d.targets) == cl)[0].tolist()
            # if len(ind) == 1:
            # print(self.d)
            # print(ind)
            sub_dataset = torch.utils.data.Subset(self.d, ind)
            self.sub_dataloader.append(torch.utils.data.DataLoader(
                sub_dataset, **sub_data_loader_params))

    def __getitem__(self, i):
        return next(iter(self.sub_dataloader[i]))

    def __len__(self):
        return len(self.sub_dataloader)


class EpisodicBatchSampler(object):
    def __init__(self, n_classes, n_way, n_episodes):
        self.n_classes = n_classes
        self.n_way = n_way
        self.n_episodes = n_episodes

    def __len__(self):
        return self.n_episodes

    def __iter__(self):
        for i in range(self.n_episodes):
            yield torch.randperm(self.n_classes)[:self.n_way]


class TransformLoader:
    def __init__(self, image_size,
                 normalize_param=dict(mean=[0.485, 0.456, 0.406], std=[
                                      0.229, 0.224, 0.225]),
                 jitter_param=dict(Brightness=0.4, Contrast=0.4, Color=0.4)):
        self.image_size = image_size
        self.normalize_param = normalize_param
        self.jitter_param = jitter_param

    def parse_transform(self, transform_type):
        if transform_type == 'ImageJitter':
            method = add_transforms.ImageJitter(self.jitter_param)
            return method

        if transform_type == 'Scale_original' or transform_type == 'Resize_original':
            return transforms.Resize([int(self.image_size), int(self.image_size)])

        method = getattr(transforms, transform_type)
        if transform_type == 'RandomSizedCrop' or transform_type == 'RandomResizedCrop':
            return method(self.image_size)
        elif transform_type == 'CenterCrop':
            return method(self.image_size)
        elif transform_type == 'Scale' or transform_type == 'Resize':
            return method([int(self.image_size*1.15), int(self.image_size*1.15)])
        elif transform_type == 'Normalize':
            return method(**self.normalize_param)
        else:
            return method()

    def get_composed_transform(self, aug=False):
        if aug:
            transform_list = ['RandomResizedCrop', 'ImageJitter',
                              'RandomHorizontalFlip', 'ToTensor', 'Normalize']
        else:
            transform_list = ['Resize', 'ToTensor', 'Normalize']

        transform_funcs = [self.parse_transform(x) for x in transform_list]
        transform = transforms.Compose(transform_funcs)
        return transform


class DataManager(object):
    @abstractmethod
    def get_data_loader(self, data_file, aug):
        pass


class SetDataManager(DataManager):
    def __init__(self, image_size, n_way=5, n_support=5, n_query=16, n_eposide=100, split=None):
        super(SetDataManager, self).__init__()
        self.image_size = image_size
        self.n_way = n_way
        self.batch_size = n_support + n_query
        self.n_eposide = n_eposide

        self.trans_loader = TransformLoader(image_size)
        self.split = split

    # parameters that would change on train/val set
    def get_data_loader(self, aug, num_workers=12):
        transform = self.trans_loader.get_composed_transform(aug)
        dataset = SetDataset(self.batch_size, transform, split=self.split)
        sampler = EpisodicBatchSampler(
            len(dataset), self.n_way, self.n_eposide)
        data_loader_params = dict(
            batch_sampler=sampler,  num_workers=num_workers, pin_memory=True)
        data_loader = torch.utils.data.DataLoader(
            dataset, **data_loader_params)
        return data_loader


if __name__ == '__main__':
    pass