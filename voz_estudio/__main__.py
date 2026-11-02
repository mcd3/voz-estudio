import argparse


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description='Voz Estudio · aplicación local')
    parser.add_argument('--port', type=int, default=3010)
    parser.add_argument('--instance', default='')
    args = parser.parse_args()
    import os
    os.environ['VOZ_INSTANCE'] = args.instance
    print(f'Voz Estudio: http://127.0.0.1:{args.port}', flush=True)
    uvicorn.run('voz_estudio.app:app', host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
