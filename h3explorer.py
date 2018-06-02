#!/usr/bin/env python3

import http.server

import argparse
import io
import os
import struct
import sys
import webbrowser

from pathlib import Path, PurePosixPath

from DefFile import DefFile
from LodFile import LodFile

parser = argparse.ArgumentParser(description='Content browser for Heroes of Might and Magic III')
parser.add_argument('game_path',
                    help='Path to the game base directory')

args = parser.parse_args()

# node_path =   virtual path in node tree e.g. /Data/H3ab_spr.lod/AVLXro11.def/0/0 ; instance of PurePosixPath
# fs_path =     path in file system (only applicable to nodes that physically exist in file system) ; instance of Path

def make_node_from_file(f, node_path):
    if node_path.suffix.lower() == '.def':
        return NodeDefFile(f, node_path)
    elif node_path.suffix.lower() == '.lod':
        return NodeLodFile(f, node_path)
    else:
        raise Exception('Format %s not understood' % node_path.suffix)

class NodeDefFileFrame:
    def __init__(self, def_, image_index, frame_index):
        self.def_ = def_
        self.image_index = image_index
        self.frame_index = frame_index

    def get_frame_rgb(self):
        return self.def_.get_frame_rgb(self.image_index, self.frame_index)

class NodeDefFileImage:
    def __init__(self, def_, image_index):
        self.def_ = def_
        self.image_index = image_index

    def open_descendant_as_node(self, name):
        return NodeDefFileFrame(self.def_, self.image_index, int(name))

class NodeDefFile:
    def __init__(self, f, node_path):
        self.def_ = DefFile(f)
        self.node_path = node_path

    def open_descendant_as_node(self, name):
        return NodeDefFileImage(self.def_, int(name))

class NodeFilesystemDirectory:
    def __init__(self, fs_path, node_path):
        self.node_path = node_path
        self.fs_path = fs_path
        self.contents = sorted(os.listdir(self.fs_path))

    def get_descendants(self):
        return self.contents

    def open_descendant_as_node(self, name):
        if name in self.contents:
            node_path = self.node_path / name
            fs_path = self.fs_path / name

            if fs_path.is_dir():
                return NodeFilesystemDirectory(fs_path, node_path)
            else:
                return make_node_from_file(open(fs_path, 'rb'), node_path)
        else:
            raise Exception('No such file')

class NodeLodFile:
    def __init__(self, f, node_path):
        self.lod = LodFile(f)
        self.node_path = node_path

    def get_descendants(self):
        return [entry['name'] for entry in self.lod.get_file_table()]

    def open_descendant_as_node(self, name):
        node_path = self.node_path / name
        raw = self.lod.get_file_bytes(name)
        return make_node_from_file(io.BytesIO(raw), node_path)

# https://stackoverflow.com/a/50260827/2524350
class Bitmap:
    def __init__(s, width, height, data):
        s._bfType = 19778 # Bitmap signature
        s._bfReserved1 = 0
        s._bfReserved2 = 0
        s._bcPlanes = 1
        s._bcSize = 12
        s._bcBitCount = 24
        s._bfOffBits = 26
        s._bcWidth = width
        s._bcHeight = height
        s._bfSize = 26+s._bcWidth*3*s._bcHeight
        s._graphics = data[::-1,:,::-1]

    def write(s, f):
        # Writing BITMAPFILEHEADER
        f.write(struct.pack('<HLHHL', s._bfType, s._bfSize, s._bfReserved1, s._bfReserved2, s._bfOffBits))
        # Writing BITMAPINFO
        f.write(struct.pack('<LHHHH', s._bcSize, s._bcWidth, s._bcHeight, s._bcPlanes, s._bcBitCount))

        for y in range(s._bcHeight):
            f.write(s._graphics[y].tobytes())
            f.write(((-s._bcWidth*3) % 4) * b'\x00')

class HtmlTable:
    def __init__(self, f, columns):
        self.f = f
        self.columns = columns

        print('<table border="1">', file=self.f)
        print('<tr>' + ''.join(['<th>%s</th>' % c for c in columns]) + '</tr>', file=self.f)

    def row(self, *row):
        print('<tr>' + ''.join(['<td>%s</td>' % str(c) for c in row]) + '</tr>', file=self.f)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        print('</table>', file=self.f)

class HtmlRenderer:
    def __init__(self, f):
        self.f = f

    def render_breadcrumb(self, path):
        def s(*args, **kwargs): print(*args, **kwargs, file=self.f)

        s('<h1>%s</h1>' % path)

    def display_NodeDefFile(self, node):
        def s(*args, **kwargs): print(*args, **kwargs, file=self.f)

        path = node.node_path
        def_ = node.def_

        self.render_breadcrumb(path)

        info = def_.describe()
        s('<h2>%d x %d, %d images, unk1=%d</h2>' % (info['w'], info['h'], len(info['images']), info['unk1']))

        with HtmlTable(self.f, ['image #', 'frame #', 'file name', 'size', 'format', 'subimage size', 'unk1', 'unk2', 'unk3']) as t:
            for image_index, image in enumerate(info['images']):
                t.row(image_index, '', '', '', '', '', image['unk_index'], image['unk2'], image['unk3'])

                for frame_index, frame in enumerate(image['frames']):
                    frame_info = def_.describe_frame(image_index, frame_index)
                    #'%dx%d' % (frame_info['full_width'], frame_info['full_height']),
                    t.row('', frame_index, frame['filename'], frame_info['size'], frame_info['format'], '%dx%d' % (frame_info['w'], frame_info['h']), frame['unk1'], '', '')

        for image_index, image in enumerate(info['images']):
            s('<h2>image #%d</h2>' % image_index)

            s('<table border="1">')
            for frame_index, frame in enumerate(image['frames']):
                # TODO: we could return the images including padding and in that case, the dimensions would be known at this point
                s('<td><img src="%s"></td>' % (path / str(image_index) / str(frame_index)))
            s('</table')

    def display_NodeFilesystemDirectory(self, node):
        def s(*args, **kwargs): print(*args, **kwargs, file=self.f)

        path = node.node_path

        self.render_breadcrumb(path)

        for name in node.get_descendants():
            s('<ul>')
            s('<li><a href="%s">%s</a></li>' % (path / name, name))
            s('</ul>')

    def display_NodeLodFile(self, node):
        def s(*args, **kwargs): print(*args, **kwargs, file=self.f)

        lod = node.lod
        path = node.node_path

        self.render_breadcrumb(path)
        s('<h2>%d files</h2>' % len(lod.get_file_table()))

        file_table = lod.get_file_table()

        with HtmlTable(self.f, ['preview', 'filename', 'start', 'uncompressed_size', 'unk2', 'compressed_size']) as t:
            for file in file_table:
                t.row('<img src="%s">' % (path / file['name'] / "0" / "0"),
                        '<a href="%s">%s</a>' % (path / file['name'], file['name']),
                        file['start'],
                        file['uncompressed_size'],
                        '%08X' % file['unk2'],
                        file['compressed_size'])

class MyHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        http.server.BaseHTTPRequestHandler.__init__(self, request, client_address, server)
        self.timeout = 10

    def do_GET(self):
        path = self.path[1:]
        paths = path.split('/') if path else []

        f = io.StringIO()

        try:
            node = NodeFilesystemDirectory(Path(args.game_path), PurePosixPath('/'))

            for part in paths:
                node = node.open_descendant_as_node(part)

            r = HtmlRenderer(f)

            if isinstance(node, NodeDefFile):
                r.display_NodeDefFile(node)
            elif isinstance(node, NodeDefFileFrame):
                frame = node.get_frame_rgb()

                self.send_response(200)
                self.send_header("Content-type", "image/bmp")
                self.send_header("Cache-Control", "public, max-age=31536000")
                self.end_headers()

                Bitmap(frame['w'], frame['h'], frame['pixels']).write(self.wfile)
                #scipy.misc.imsave(self.wfile, frame['pixels'], format='BMP')

                return
            elif isinstance(node, NodeFilesystemDirectory):
                r.display_NodeFilesystemDirectory(node)
            elif isinstance(node, NodeLodFile):
                r.display_NodeLodFile(node)
            else:
                raise Exception('Dunno how to display path %s' % path)
        except Exception as e:
            import traceback
            print('<pre>', file=f)
            print(traceback.format_exc(), file=f)
            print('</pre>', file=f)

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(f.getvalue().encode())

def run(server_class=http.server.HTTPServer, handler_class=MyHTTPRequestHandler):
    server_address = ('', 8000)
    httpd = server_class(server_address, handler_class)
    webbrowser.open('http://localhost:8000')
    print('Listening on port', server_address[1])
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()

run()
