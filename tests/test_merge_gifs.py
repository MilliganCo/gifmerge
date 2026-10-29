import importlib.util
from pathlib import Path
import random
import tempfile
import unittest
from collections import Counter

spec = importlib.util.spec_from_file_location('merge_gifs', Path(__file__).parents[1] / 'merge_gifs.py')
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)


class OrderingTests(unittest.TestCase):
    def test_feasible_orders_have_no_adjacent_duplicates(self):
        for items in (list('aaabbb'), list('aaaabbcc'), list('aaaaabbbb')):
            for seed in range(100):
                with self.subTest(items=items, seed=seed):
                    random.seed(seed)
                    actual = merge.shuffle_no_consecutive(items)
                    self.assertEqual(Counter(actual), Counter(items))
                    self.assertTrue(all(a != b for a, b in zip(actual, actual[1:])))

    def test_impossible_order_keeps_every_item(self):
        items = list('aaaaab')
        self.assertEqual(Counter(merge.shuffle_no_consecutive(items)), Counter(items))
        self.assertEqual(merge.shuffle_no_consecutive([]), [])

    def test_input_discovery_excludes_previous_output_and_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ('one.gif', 'two.GIF', 'merged.gif', 'readme.txt'):
                (folder / name).touch()
            (folder / 'directory.gif').mkdir()
            self.assertEqual([p.name for p in merge.find_gif_inputs(folder, folder / 'merged.gif')], ['one.gif', 'two.GIF'])


if __name__ == '__main__':
    unittest.main()
