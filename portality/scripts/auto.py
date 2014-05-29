from portality.autodiscovery import autodiscovery
import json

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument("-u", "--url", help="url to autodetect from")

    args = parser.parse_args()

    if not args.url:
        print "Please specify a url with the -u option"
        exit()

    register = autodiscovery.discover(args.url)
    print json.dumps(register.raw)