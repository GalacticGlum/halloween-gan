"""Process and clean a raw dataset of halloween costumes."""

import os
import time
import tqdm
import click
import shutil
import argparse
from PIL import Image
from pathlib import Path
from u2net_wrapper import U2Net
from face_detection import FaceDetector

class ReadableDirectory(argparse.Action):
    """Makes sure that a directory argument is a valid path and readable."""
    def __call__(self, parser, namespace, value, option_string=None):
        if not value.is_dir():
            raise argparse.ArgumentTypeError(f'\'{value.resolve()}\' is not a valid path!')

        if not os.access(value, os.R_OK):
            raise argparse.ArgumentTypeError(f'\'{value.resolve()}\' is not a readable directory!')

        setattr(namespace, self.dest, value)

def get_files(source, patterns):
    """Get all the paths matching the given list of glob patterns."""

    for pattern in patterns:
        files = source.glob(f'**/{pattern}')
        for file in files:
            yield file

def _rmtree(path, ignore_errors=False, onerror=None, timeout=10):
    """
    A wrapper method for 'shutil.rmtree' that waits up to the specified
    `timeout` period, in seconds.
    """
    shutil.rmtree(path, ignore_errors, onerror)

    if path.is_dir():
        print(f'shutil.rmtree - Waiting for \'{path}\' to be removed...')
        # The destination path has yet to be deleted. Wait, at most, the timeout period.
        timeout_time = time.time() + timeout
        while time.time() <= timeout_time:
            if not path.is_dir():
                break

def main():
    """Main entrypoint when running this module from the terminal."""

    parser = argparse.ArgumentParser(description='Process and a clean a raw dataset of halloween costumes')
    parser.add_argument('dataset_source', help='The path to the directory containing the source dataset.', type=Path, action=ReadableDirectory)
    parser.add_argument('--destination', '-d', dest='dataset_destination', help='The path to the directory which the cleaned '
                        'dataset should be saved. If this is not specified, the cleaned files are saved in the same parent '
                        'folder as the source.', type=Path, default=None)
    parser.add_argument('--file-glob-patterns', nargs='+', type=str, default=['*.png', '*.jpeg', '*.jpg'],
                        help='The glob patterns to use to find files in the source directory.')
    parser.add_argument('--no-remove-transparency', action='store_false', dest='remove_transparency',
                        help='Remove transparency and replace it with a colour.')
    parser.add_argument('--bg-colour', type=str, default='WHITE', help='The colour to replace transparency with.')
    parser.add_argument('--u2net-size', type=str, default='large', help='The size of the pretrained U-2-net model. Either \'large\' or \'small\'.')
    parser.add_argument('--yes', '-y', action='store_true', help='Yes to all.')
    args = parser.parse_args()

    # Create a destination path if none was provided.
    if args.dataset_destination is None:
        args.dataset_destination = args.dataset_source.parent / (args.dataset_source.stem + '_cleaned')

    if args.dataset_destination.exists() and any(args.dataset_destination.iterdir()):
        if not args.yes:
            click.confirm(
                f'The destination path (\'{args.dataset_destination.resolve()}\') '
                'already exists! Would you like to continue? This will overwrite the directory.',
                abort=True
            )

        _rmtree(args.dataset_destination)

    args.dataset_destination.mkdir(exist_ok=True, parents=True)

    u2net = U2Net(pretrained_model_name=args.u2net_size)
    face_detector = FaceDetector()

    files = list(get_files(args.dataset_source, args.file_glob_patterns))
    with tqdm.tqdm(files) as progress:
        for file in progress:
            progress.set_description(f'Processing {file.name}')

            # Skip images that don't have a single face in them...
            face_detection_results = face_detector.detect_faces(file)
            if len(face_detection_results) != 1: continue

            segmentation_map = u2net.segment_image(file)
            # Remove background from image (using U2Net)
            image = u2net.remove_background(file, segmentation_map)

            # Crop image to bounding box (using U2Net)
            bounding_box = u2net.get_bounding_box(segmentation_map)
            image = image.crop(bounding_box)

            if args.remove_transparency:
                # Replace transparency with colour
                background_image = Image.new('RGBA', image.size, args.bg_colour)
                background_image.paste(image, (0, 0), image)
                image = background_image.convert('RGB')

            # Output processed image
            destination = args.dataset_destination / (file.stem + '.png')
            image.save(str(destination))

if __name__ == '__main__':
    main()
