from abc import ABCMeta, abstractmethod
import os
import gzip
import tarfile
import urllib.request
import math
import numpy as np
from .transforms import Compose, Flatten, ToFloat, Normalise
from .utils import replace_symbols, replace_email, replace_numbers, replace_tab, single_spacing, fix_multidots

# matplotlib is not in dependency list (optional)
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None


# -------------------------------------------------------------
# Helper functions
# -------------------------------------------------------------


# path to the directory to put any cache files.
CACHE_DIR = os.path.join(os.path.expanduser('~'), '.bareml')


def show_progress(block_num, block_size, total_size):
    bar_template = "\r[{}] {:.2f}%"

    downloaded = block_num * block_size
    p = downloaded / total_size * 100
    i = int(downloaded / total_size * 30)
    if p >= 100.0: p = 100.0
    if i >= 30: i = 30
    bar = "#" * i + "." * (30 - i)
    print(bar_template.format(bar, p), end='')


def get_file(url, file_name=None):
    """
    Download a file from the given url if it is not in the cache.
    The file at the given url is downloaded to the '~/.bareml'.

    Parameters
    ----------
    url: str
        url of the file.
    
    file_name: str
        name of the file. If none, the original file name is used.

    Returns
    -------
    file_path: str
        Absolute path to the saved file.
    """
    if file_name is None:
        file_name = url[url.rfind('/') + 1:]
    file_path = os.path.join(CACHE_DIR, file_name)

    if not os.path.exists(CACHE_DIR):
        os.mkdir(CACHE_DIR)

    if os.path.exists(file_path):
        return file_path

    print("Downloading: " + file_name)
    try:
        urllib.request.urlretrieve(url, file_path, show_progress)
    except (Exception, KeyboardInterrupt) as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise
    print(" Done")

    return file_path


# -------------------------------------------------------------
# Core classes: Dataset / DataLoader
# -------------------------------------------------------------


class Dataset(metaclass=ABCMeta):

    def __init__(self, train=True, transform=None, target_transform=None):
        self.train = train

        self.transform = transform 
        self.target_transform = target_transform
        if self.transform is None:
            self.transform = lambda x:x
        if self.target_transform is None:
            self.target_transform = lambda x:x

        self.data = None
        self.target = None
        self.prepare()

    def __getitem__(self, index):
        if self.target is None:
            return self.transform(self.data[index]), None
        else:
            return self.transform(self.data[index]), self.target_transform(self.target[index])

    def __len__(self):
        return len(self.data)

    @abstractmethod
    def prepare(self):
        """ implement data creation for self.data and self.target """
        pass


class LargeDataset(Dataset):

    def __init__(self, train=True, transform=None, target_transform=None):
        super().__init__(train, transform, target_transform)

    def __getitem__(self, index):
        if self.get_target(0) is None:
            return self.transform(self.get_data(index)), None
        else:
            return self.transform(self.get_data(index)), self.target_transform(self.get_target(index))

    @abstractmethod
    def __len__(self):
        pass

    @abstractmethod
    def get_data(self, index):
        pass

    def get_target(self, index):
        return None

    @abstractmethod
    def prepare(self):
        """ implement data creation and set self.size """
        pass


class Corpus(Dataset):
    def __init__(self, dataset, transform=None, target_transform=None):
        self.dataset = dataset
        self.word2id = {}
        self.id2word = {}
        super().__init__(transform=transform, target_transform=target_transform)
        
    def _process_words(self, words):
        corpus = []
        for word in words:
            if word not in self.word2id:
                new_id = len(self.word2id)
                self.word2id[word] = new_id
                self.id2word[new_id] = word
            corpus.append(self.word2id[word])
        
        self.data.append(corpus)
                
    def prepare(self):
        
        self.target = self.dataset.target
        self.data = []
        
        for i, (x, t) in enumerate(self.dataset):
            self._process_words(x[0].split(' '))
            if i % 1000 == 0 and i != 0:
                print(i, "/" + str(len(self.dataset)) + " data processed.")

        self.corpus = [item for sublist in self.data for item in sublist]
                
    def get_word(self, word_id):
        return self.id2word[word_id]
    
    def get_id(self, word):
        return self.word2id[word]


class DataLoader:
    def __init__(self, dataset, batch_size, shuffle=True):
        self.dataset = dataset
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.data_size = len(dataset)
        self.max_iter = math.ceil(self.data_size / batch_size)

        self.reset()

    def reset(self):
        self.iteration = 0
        if self.shuffle:
            self.index = np.random.permutation(len(self.dataset))
        else:
            self.index = np.arange(len(self.dataset))

    def __iter__(self):
        return self

    def __next__(self):
        if self.iteration >= self.max_iter:
            self.reset()
            raise StopIteration

        i, batch_size = self.iteration, self.batch_size
        batch_index = self.index[i*batch_size : (i+1)*batch_size]
        batch_x, batch_t = self.dataset[batch_index]

        self.iteration += 1
        return batch_x, batch_t

    def next(self):
        return self.__next__()


# -------------------------------------------------------------
# Datasets: MNIST, 20Newsgroups
# -------------------------------------------------------------


class MNIST(Dataset):

    def __init__(self, train=True,
                 transform=Compose([Flatten(), ToFloat(), Normalise(0., 255.)]),
                 target_transform=None, digits=None):
        super().__init__(train, transform, target_transform)

        if digits is not None:
            self._specify_digits(digits)

    def prepare(self):
        url = 'http://yann.lecun.com/exdb/mnist/'
        train_files = {'target': 'train-images-idx3-ubyte.gz',
                       'label': 'train-labels-idx1-ubyte.gz'}
        test_files = {'target': 't10k-images-idx3-ubyte.gz',
                      'label': 't10k-labels-idx1-ubyte.gz'}

        files = train_files if self.train else test_files
        data_path = get_file(url + files['target'])
        label_path = get_file(url + files['label'])

        self.data = self._load_data(data_path)
        self.target = self._load_label(label_path)

    def _load_label(self, filepath):
        with gzip.open(filepath, 'rb') as f:
            labels = np.frombuffer(f.read(), np.uint8, offset=8)
        return labels

    def _load_data(self, filepath):
        with gzip.open(filepath, 'rb') as f:
            data = np.frombuffer(f.read(), np.uint8, offset=16)
        data = data.reshape(-1, 1, 28, 28)
        return data

    def _specify_digits(self, digits):
        """
        Parameters
        ----------
        digits: int [0,9] or list of int [0,9]
        """
        if isinstance(digits, list) or isinstance(digits, np.ndarray):
            digits = list(set(digits)) # remove duplicates if any
            idx = np.array([])
            for d in digits:
                idx = np.concatenate([idx, np.where(self.target == d)[0]])
        else: # digits is an int
            idx = np.where(self.target == digits)[0]

        idx = idx.astype(int)

        self.data = self.data[idx]
        self.target = self.target[idx]

    def show(self, row=10, col=10):
        if plt is None:
            print('Visualisation not available. Install matplotlib.')
        else:
            H, W = 28, 28
            img = np.zeros((H * row, W * col))
            for r in range(row):
                for c in range(col):
                    img[r * H:(r + 1) * H, c * W:(c + 1) * W] = self.data[
                        np.random.randint(0, len(self.data) - 1)].reshape(H, W)
            plt.imshow(img, cmap='gray', interpolation='nearest')
            plt.axis('off')
            plt.show()

    @staticmethod
    def labels():
        return {0: '0', 1: '1', 2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 7: '7', 8: '8', 9: '9'}


class NewsGroups(LargeDataset):
    """ 20 News groups data set"""

    headers = ('from:', 'subject:', 'organization:', 'lines:', 'nntp-posting-host:', 
               'reply-to:', 'in-reply-to:', 'keywords:', 'nf-id:', 'nf-from:', 'originator:',
               'in article ', 'distribution:', '> in article', '>>in article', '>> in article',
               'article-i.d.:')

    def __init__(self, train=True,
                 transform=None,
                 target_transform=None,
                 preprocess=True):
        super().__init__(train, transform, target_transform)
        self.preprocess = preprocess

    def prepare(self):
        url = 'http://qwone.com/~jason/20Newsgroups/20news-bydate.tar.gz'
        filepath = get_file(url)

        dataname = '20news-bydate-train' if self.train else '20news-bydate-test'
        datapath = os.path.join(CACHE_DIR, dataname)

        if not os.path.exists(datapath):
            tar = tarfile.open(filepath, "r:gz")
            tar.extractall(CACHE_DIR)
            tar.close()

        folders = [f for f in os.listdir(datapath)]

        self.filepaths = []
        self.target = []
        self.labels = {}
        for i, folder_name in enumerate(folders):
            self.labels[i] = folder_name
            folderpath = os.path.join(datapath, folder_name)
            self.filepaths += [os.path.join(folderpath, file_name) for file_name in os.listdir(folderpath)]
            self.target += [i] * len(os.listdir(folderpath))

    def _is_header(self, line):
        return line.lower().startswith(NewsGroups.headers)

    def _clean(self, s):
        s = replace_tab(s)
        s = replace_email(s)
        s = s.replace("'", '') # don't -> dont
        s = replace_symbols(s)
        s = s.replace(',', ' ') # remove commas
        s = s.replace('.', ' .') # consider . as a single word
        s = replace_numbers(s, '<N>')
        s = fix_multidots(s)
        s = single_spacing(s)
        return s.strip()
    
    def _preprocess(self, lines):
        lines = [self._clean(line) for line in lines if not self._is_header(line)]
        return ' '.join([line for line in lines if line != '']).lower()

    def __len__(self):
        return len(self.filepaths)

    def get_data(self, index):
        filepaths = self.filepaths[index]
        if not isinstance(filepaths, list):
            filepaths = [filepaths]
        
        if self.preprocess:
            return [self._preprocess(open(f, 'r', encoding='latin1').readlines()) for f in filepaths]
        else:
            return [open(f, 'r', encoding='latin1').read() for f in filepaths]

    def get_target(self, index):
        return self.target[index]

    def labels(self):
        return self.labels


class NewsGroupsWordInference(Dataset):
    def __init__(self, train=True, window_size=5):
        self.window_size = window_size
        super().__init__(train)

    def prepare(self):

        print('-- Step 1/2 --')
        self.corpus = Corpus(NewsGroups(self.train))
        
        print('-- Step 2/2 --')
        target_col = self.window_size//2
        for i, (x, _) in enumerate(self.corpus):
            y = np.array([x[i:i+self.window_size] for i in range(len(x) - self.window_size + 1)])
            if len(y) != 0:
                if self.data is None:
                    self.data = np.delete(y, target_col, 1)
                    self.target = y[:,target_col]
                else:
                    self.data = np.concatenate((self.data, np.delete(y, target_col, 1)))
                    self.target = np.concatenate((self.target, y[:,target_col]))

            if i % 1000 == 0 and i != 0:
                print(i, "/" + str(len(self.corpus)) + " data processed.")





