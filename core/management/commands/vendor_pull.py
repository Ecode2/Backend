import os
import subprocess
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Pull vendor files for static assets"

    def handle(self, *args, **kwargs):
        # Define the commands to be executed
        commands = [
            "rm -rf src/static/vendor",
            "mkdir -p src/static/vendor/htmx/",
            "mkdir -p src/static/vendor/flowbite/",
            "curl -L https://unpkg.com/htmx.org@1.8.2 -o ./static/vendor/htmx/htmx.min.js",
            "curl -L https://cdnjs.cloudflare.com/ajax/libs/flowbite/2.3.0/flowbite.min.js -o ./static/vendor/flowbite/flowbite.min.js",
        ]

        # Execute each command
        for command in commands:
            self.stdout.write(f"Executing: {command}")
            result = subprocess.run(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if result.returncode != 0:
                self.stderr.write(
                    self.style.ERROR(
                        f"Error executing command: {command}\n{result.stderr.decode()}"
                    )
                )
                return
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"Successfully executed: {command}")
                )
