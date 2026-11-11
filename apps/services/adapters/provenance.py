import json
import os
import asyncio

class ProvenanceAdapter:
    async def write_manifest(self, output_video_path: str, models_used: list, actions: list) -> str:
        manifest_path = f"{output_video_path}.manifest.json"
        manifest_data = {
            "ai_disclosure": True,
            "models_used": models_used,
            "actions": actions
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f, indent=2)

        # Add metadata comment="AI-dubbed" to final video
        temp_output = f"{output_video_path}.temp.mp4"
        cmd = [
            "ffmpeg", "-y", "-i", output_video_path,
            "-metadata", 'comment="AI-dubbed"',
            "-codec", "copy",
            temp_output
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        if process.returncode == 0:
            os.replace(temp_output, output_video_path)

        return manifest_path
