"""Local reproducibility script: fixed pandas fixture only; no network/model request."""
import sys
import pandas as pd
from replay import run_offline


def main():
    report = run_offline()
    red = report['red']
    green = report['green']
    print('EXPIREMEM GUARDIAN / PUBLIC OFFLINE DEMO')
    print('Python:', sys.version.split()[0])
    print('pandas:', pd.__version__)
    print('Fixture:', 'DataFrame.append removed API')
    print('RED exit code:', red['returncode'])
    print('RED error:', red['stderr'].strip().splitlines()[-1])
    print('Decision:', report['decision']['decision'])
    print('Mode:', report['outcome'])
    print('Proposal origin:', report['proposal_origin'])
    print('GREEN exit code:', green['returncode'])
    print('GREEN output:', green['stdout'].strip())
    assert red['returncode'] != 0
    assert green['returncode'] == 0
    assert report['outcome'] == 'GREEN_OFFLINE_REPLAY'
    assert report['proposal_origin'] == 'OFFLINE_REPLAY_RULE'


if __name__ == '__main__':
    main()
