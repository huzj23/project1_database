"""Dataset layout, trajectory, config, and metadata serialization."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import yaml

from physim.physics import SimulationResult
from physim.render import RenderResult


def _write_json(path: Path, data: dict | list) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


class DatasetWriter:
    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)

    def write(
        self,
        kb,
        render: RenderResult,
        simulation: SimulationResult,
        config: dict,
        metadata: dict,
    ) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=False)
        available_modalities = {
            "rgb": render.rgb,
            "depth": render.depth,
            "segmentation": render.segmentation,
        }
        requested_modalities = tuple(config["output"].get("modalities", ("rgb",)))
        unknown = sorted(set(requested_modalities) - set(available_modalities))
        if unknown:
            raise ValueError(f"Renderer did not provide requested modalities: {unknown}")
        for name in requested_modalities:
            values = available_modalities[name]
            target = self.output_dir / name
            target.mkdir()
            kb.write_image_dict({name: values}, target)
        if config["output"].get("write_video", True):
            self._write_rgb_video(
                render.rgb,
                self.output_dir / "video.mp4",
                int(config["timing"]["video_fps"]),
            )
        trajectory_rows = []
        for index, state in enumerate(simulation.trajectory):
            row = state.to_dict()
            if len(simulation.trajectory) == 1:
                acceleration = (0.0, 0.0, 0.0)
            else:
                previous_index = max(0, index - 1)
                next_index = min(len(simulation.trajectory) - 1, index + 1)
                previous = simulation.trajectory[previous_index]
                following = simulation.trajectory[next_index]
                delta_time = following.time_seconds - previous.time_seconds
                acceleration = tuple(
                    (following.linear_velocity[axis] - previous.linear_velocity[axis])
                    / max(delta_time, 1e-12)
                    for axis in range(3)
                )
            row["acceleration"] = acceleration
            trajectory_rows.append(row)
        _write_json(self.output_dir / "trajectory.json", trajectory_rows)
        # A driven-support scenario records a SECOND body (the turntable disc).
        # Without this the disc's motion would be silently dropped from the
        # dataset even though it was simulated and rendered, so the saved data
        # would not describe the clip.  The block is skipped entirely for every
        # single-body scenario, so their outputs are byte-identical.
        support_trajectory = getattr(simulation, "support_trajectory", ())
        if support_trajectory:
            support_rows = []
            for index, state in enumerate(support_trajectory):
                row = state.to_dict()
                if len(support_trajectory) == 1:
                    acceleration = (0.0, 0.0, 0.0)
                else:
                    previous_index = max(0, index - 1)
                    next_index = min(len(support_trajectory) - 1, index + 1)
                    previous = support_trajectory[previous_index]
                    following = support_trajectory[next_index]
                    delta_time = following.time_seconds - previous.time_seconds
                    acceleration = tuple(
                        (
                            following.linear_velocity[axis]
                            - previous.linear_velocity[axis]
                        )
                        / max(delta_time, 1e-12)
                        for axis in range(3)
                    )
                row["acceleration"] = acceleration
                row["body"] = "support"
                support_rows.append(row)
            _write_json(self.output_dir / "support_trajectory.json", support_rows)
        _write_json(self.output_dir / "collisions.json", list(simulation.collisions))
        _write_json(self.output_dir / "metadata.json", metadata)
        with (self.output_dir / "config.yaml").open("w", encoding="utf-8") as stream:
            yaml.safe_dump(config, stream, sort_keys=False)

    @staticmethod
    def _write_rgb_video(values, path: Path, fps: int) -> None:
        frames = np.asarray(values)
        if frames.ndim != 4 or frames.shape[-1] < 3:
            raise ValueError(f"Expected RGB video array [T,H,W,C], got {frames.shape}")
        frames = frames[..., :3]
        if np.issubdtype(frames.dtype, np.floating):
            frames = np.clip(frames, 0.0, 1.0) * 255.0
        frames = np.ascontiguousarray(frames.astype(np.uint8))
        try:
            import cv2

            height, width = frames.shape[1:3]
            writer = cv2.VideoWriter(
                str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
            )
            if not writer.isOpened():
                raise RuntimeError("OpenCV could not open the MP4 writer")
            try:
                for frame in frames:
                    writer.write(frame[..., ::-1])
            finally:
                writer.release()
            if path.is_file() and path.stat().st_size > 0:
                return
        except (ImportError, RuntimeError):
            pass

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("Writing video.mp4 requires OpenCV or ffmpeg")
        height, width = frames.shape[1:3]
        completed = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                f"{width}x{height}",
                "-r",
                str(fps),
                "-i",
                "-",
                "-an",
                "-vcodec",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            input=frames.tobytes(),
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(
                "ffmpeg failed to write video.mp4: "
                + completed.stderr.decode("utf-8", errors="replace")[-1000:]
            )
