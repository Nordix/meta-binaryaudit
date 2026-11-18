import subprocess


def run_command(cmd, input, output):
    ''' Runs commands and gets output.

    Parameters:
    # Input cmdn is a list
        cmd (array): The command to be run.
        input: The input for stdin of Popen.
        output: The output for stdout of Popen.
    Returns:
        poen_output: The output of Popen.
        exit_code: The exit code of Popen.
    '''
    popen_output = subprocess.Popen(cmd, stdin=input, stdout=output)
    popen_output.wait()
    exit_code = popen_output.returncode
    return popen_output, exit_code
