import docker
import os
import io
import tarfile
import uuid
import time

class EnvironmentManager:
    def __init__(self):
        self.client = docker.from_env()
        self.environments = {} # Stores environment_id -> {'container': container_obj, 'volume': volume_obj}

    def create_isolated_environment(self, environment_id: str, base_image: str = "python:3.9-slim-buster") -> str:
        try:
            # Create a named volume for persistence
            volume_name = f"env_{environment_id}_vol"
            # Check if volume already exists to avoid errors on re-runs for the same ID
            try:
                volume = self.client.volumes.get(volume_name)
                print(f"Volume '{volume_name}' already exists, reusing.")
            except docker.errors.NotFound:
                volume = self.client.volumes.create(volume_name)
                print(f"Volume '{volume_name}' created.")
            
            # Check if container already exists and remove it if it does
            try:
                existing_container = self.client.containers.get(environment_id)
                print(f"Existing container '{environment_id}' found, removing it.")
                existing_container.stop()
                existing_container.remove()
            except docker.errors.NotFound:
                pass # No existing container, proceed

            # Run the container with the volume mounted
            container = self.client.containers.run(
                base_image,
                detach=True,
                name=environment_id,
                volumes={volume_name: {'bind': '/app', 'mode': 'rw'}},
                tty=True, # Keep container running
                command="/bin/bash" # A simple command to keep it alive
            )
            self.environments[environment_id] = {'container': container, 'volume': volume}
            print(f"Environment '{environment_id}' created successfully.")
            return environment_id
        except docker.errors.APIError as e:
            print(f"Error creating environment: {e}")
            return None

    def execute_command_in_environment(self, environment_id: str, command: str, workdir: str = "/app") -> dict:
        if environment_id not in self.environments:
            return {"stdout": "", "stderr": f"Environment '{environment_id}' not found.", "exit_code": 1}
        
        container = self.environments[environment_id]['container']
        try:
            # exec_run returns (exit_code, (stdout_bytes, stderr_bytes))
            # stream=False will return a tuple of (exit_code, output_bytes)
            # demux=False means stdout and stderr are merged if not separated.
            exit_code, output_bytes = container.exec_run(
                command, 
                workdir=workdir, 
                stream=False, 
                demux=False, 
                environment={"PYTHONUNBUFFERED": "1"} # Ensure Python output is not buffered
            )
            stdout = output_bytes.decode('utf-8', errors='ignore').strip() # Ignore errors for wider compatibility
            stderr = "" # As demux=False, stderr is part of stdout for simple exec_run
            
            # A more robust way to get separate stdout/stderr if needed:
            # result = container.exec_run(command, workdir=workdir, stream=True, demux=True)
            # stdout_chunks = []
            # stderr_chunks = []
            # for chunk_type, chunk_data in result.output:
            #     if chunk_type == 1: # stdout
            #         stdout_chunks.append(chunk_data.decode('utf-8'))
            #     elif chunk_type == 2: # stderr
            #         stderr_chunks.append(chunk_data.decode('utf-8'))
            # stdout = "".join(stdout_chunks)
            # stderr = "".join(stderr_chunks)

            return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}
        except docker.errors.APIError as e:
            return {"stdout": "", "stderr": f"Error executing command: {e}", "exit_code": 1}

    def write_file_to_environment(self, environment_id: str, file_path: str, content: str) -> None:
        if environment_id not in self.environments:
            raise ValueError(f"Environment '{environment_id}' not found.")
        
        container = self.environments[environment_id]['container']
        
        # Ensure directory exists in the container
        dir_name = os.path.dirname(file_path)
        if dir_name and dir_name != "/":
            self.execute_command_in_environment(environment_id, f"mkdir -p {dir_name}")

        # Create a tar archive in memory
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            file_data = content.encode('utf-8')
            tarinfo = tarfile.TarInfo(name=os.path.basename(file_path)) # Only basename for tar entry
            tarinfo.size = len(file_data)
            tar.addfile(tarinfo, io.BytesIO(file_data))
        
        # Move stream position to the beginning before sending
        tar_stream.seek(0)
        
        # put_archive needs the full path to the directory where the tar should be extracted
        container.put_archive(dir_name if dir_name else '/', tar_stream.getvalue())
        print(f"File '{file_path}' written to environment '{environment_id}'.")


    def read_file_from_environment(self, environment_id: str, file_path: str) -> str:
        if environment_id not in self.environments:
            raise ValueError(f"Environment '{environment_id}' not found.")
        
        container = self.environments[environment_id]['container']
        try:
            # get_archive returns a tuple (stream, stat)
            strm, stat = container.get_archive(file_path)
            
            file_obj = io.BytesIO()
            for chunk in strm:
                file_obj.write(chunk)
            file_obj.seek(0)
            
            # Extract from tar stream
            with tarfile.open(fileobj=file_obj, mode='r') as tar:
                # Assuming the archive contains only the requested file at the root of the tar
                members = tar.getmembers()
                if not members:
                    raise FileNotFoundError(f"File '{file_path}' not found in archive.")
                member = members[0] 
                return tar.extractfile(member).read().decode('utf-8')
        except docker.errors.NotFound:
            raise FileNotFoundError(f"File '{file_path}' not found in container '{environment_id}'.")
        except docker.errors.APIError as e:
            print(f"Error reading file '{file_path}': {e}")
            raise
        except tarfile.ReadError:
            print(f"File '{file_path}' not found or invalid archive.")
            raise
    
    def destroy_environment(self, environment_id: str) -> None:
        if environment_id in self.environments:
            container = self.environments[environment_id]['container']
            volume = self.environments[environment_id]['volume']
            try:
                container.stop()
                container.remove()
                volume.remove() # Remove the volume too
                del self.environments[environment_id]
                print(f"Environment '{environment_id}' destroyed successfully.")
            except docker.errors.APIError as e:
                print(f"Error destroying environment: {e}")
        else:
            print(f"Environment '{environment_id}' not found for destruction (might already be removed).")

# --- Test Script ---
if __name__ == "__main__":
    env_manager = EnvironmentManager()
    test_env_id = f"dev_env_{str(uuid.uuid4())[:8]}" # Unique ID for testing

    print("\n--- Testing Environment Creation ---")
    created_id = env_manager.create_isolated_environment(test_env_id)
    if created_id:
        print(f"Created environment with ID: {created_id}")
    else:
        print("Failed to create environment. Exiting.")
        exit()

    print("\n--- Testing File Writing ---")
    file_content = """
print('Hello from the agent-generated app!')
import os
import time

if __name__ == '__main__':
    print('Application started.')
    # Create a test file
    with open('/app/test_output.txt', 'w') as f:
        f.write('This is a test output from the app.')
    print('test_output.txt created.')
    time.sleep(1) # Give time for file system operations
"""
    file_path = "/app/main.py"
    try:
        env_manager.write_file_to_environment(created_id, file_path, file_content)
    except Exception as e:
        print(f"Failed to write file: {e}")
        env_manager.destroy_environment(created_id)
        exit()

    print("\n--- Testing File Reading (initial) ---")
    try:
        read_content = env_manager.read_file_from_environment(created_id, file_path)
        print(f"Read content from '{file_path}':\n{read_content}")
        assert read_content.strip() == file_content.strip()
    except Exception as e:
        print(f"Failed to read file: {e}")
        env_manager.destroy_environment(created_id)
        exit()

    print("\n--- Testing Command Execution (ls -l /app) ---")
    result_ls = env_manager.execute_command_in_environment(created_id, "ls -l /app")
    print(f"Command 'ls -l /app' output:\nStdout:\n{result_ls['stdout']}\nStderr:\n{result_ls['stderr']}\nExit Code: {result_ls['exit_code']}")
    assert "main.py" in result_ls['stdout']
    assert result_ls['exit_code'] == 0

    print("\n--- Testing Command Execution (python /app/main.py) ---")
    result_run = env_manager.execute_command_in_environment(created_id, "python /app/main.py")
    print(f"Command 'python /app/main.py' output:\nStdout:\n{result_run['stdout']}\nStderr:\n{result_run['stderr']}\nExit Code: {result_run['exit_code']}")
    assert "Hello from the agent-generated app!" in result_run['stdout']
    assert "Application started." in result_run['stdout']
    assert "test_output.txt created." in result_run['stdout']
    assert result_run['exit_code'] == 0

    print("\n--- Testing File Reading (generated by app) ---")
    generated_file_path = "/app/test_output.txt"
    try:
        generated_content = env_manager.read_file_from_environment(created_id, generated_file_path)
        print(f"Read content from '{generated_file_path}':\n{generated_content}")
        assert "This is a test output from the app." in generated_content
    except Exception as e:
        print(f"Failed to read generated file: {e}")
        env_manager.destroy_environment(created_id)
        exit()

    print("\n--- Testing Command Execution (non-existent command) ---")
    result_fail = env_manager.execute_command_in_environment(created_id, "nonexistent_command")
    print(f"Command 'nonexistent_command' output:\nStdout:\n{result_fail['stdout']}\nStderr:\n{result_fail['stderr']}\nExit Code: {result_fail['exit_code']}")
    assert result_fail['exit_code'] != 0 # Should fail

    print("\n--- Testing Environment Destruction ---")
    env_manager.destroy_environment(created_id)

    print("\n--- All prototype tests completed. ---")