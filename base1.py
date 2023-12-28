import os
import uuid
from flask import Flask, request, jsonify, send_from_directory
from concurrent.futures import ThreadPoolExecutor
import ffmpeg

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'

os.environ['PATH'] += os.pathsep + 'D:/ASoft/ffmpeg/bin'

EXECUTOR = ThreadPoolExecutor(max_workers=os.cpu_count() * 2)


class ClipTask:
    def __init__(self, id, video_url, start_time, end_time, output_filepath):
        self.id = id
        self.video_url = video_url
        self.start_time = start_time
        self.end_time = end_time
        self.output_filepath = output_filepath
        self.output_filename = os.path.basename(output_filepath)
        self.status = 'pending'
        self.error_message = None
        self.download_url = '/download/' + self.output_filename

    def to_dict(self):
        return {
            'id': self.id,
            'video_url': self.video_url,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'output_filepath': self.output_filepath,
            'status': self.status,
            'error_message': self.error_message,
            'download_url': self.download_url,
            'output_filename': self.output_filename
        }


CLIP_TASKS = {}


def clip_video_function(task):
    task_id = task.id
    task = CLIP_TASKS.get(task_id)
    if not task:
        return
    task.status = 'running'

    try:
        input_clip = ffmpeg.input(task.video_url, ss=task.start_time)
        output_clip = ffmpeg.output(input_clip, task.output_filepath, to=task.end_time)
        ffmpeg.run(output_clip)
        task.status = 'completed'

    except ffmpeg.Error as e:
        task.status = 'failed'
        task.error_message = str(e)


@app.route('/clip-video', methods=['POST'])
def handle_clip_video():
    data = request.get_json()
    video_url = data['video_url']
    start_time = data['start_time']
    end_time = data['end_time']

    output_filename = f"{uuid.uuid4()}.mp4"
    output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

    task = ClipTask(str(uuid.uuid4()), video_url, start_time, end_time, output_filepath)
    task.download_url = '/download/' + os.path.basename(task.output_filepath)  # Set download URL immediately
    CLIP_TASKS[task.id] = task

    EXECUTOR.submit(clip_video_function, task)

    response = {
        'message': 'Clip task has been submitted.',
        'task_id': task.id,
        'download_url': request.url_root.rstrip('/') + task.download_url
    }

    return jsonify(response)


@app.route('/clip-task/<task_id>', methods=['GET'])
def get_clip_task(task_id):
    task = CLIP_TASKS.get(task_id)
    if not task:
        return jsonify({'error': f'Clip task {task_id} not found.'}), 404
    else:
        return jsonify(task.to_dict())


@app.route('/download/<path:filename>', methods=['GET'])
def download(filename):
    task = next((task for task in CLIP_TASKS.values() if task.output_filename == filename), None)
    if not task:
        return jsonify({'error': f"Clip task with output file '{filename}' not found."}), 404
    elif task.status != 'completed':
        return jsonify({
                           'error': f"Clip task {task.id} is still in progress. The status is '{task.status}'. Please try downloading later."}), 403
    else:
        return send_from_directory(os.path.abspath(app.config['UPLOAD_FOLDER']), filename)


if __name__ == "__main__":
    if not os.path.isdir('uploads/'):
        os.makedirs('uploads/')
    app.run(debug=True, threaded=True)