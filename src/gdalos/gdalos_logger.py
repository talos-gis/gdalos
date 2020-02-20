import logging


def set_logger_console(logger, level=logging.INFO):
    logger.setLevel(logging.DEBUG)
    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(level)

    # create formatter and add it to the handlers
    formatter = logging.Formatter("%(message)s")
    ch.setFormatter(formatter)

    # add the handlers to logger
    logger.addHandler(ch)
    return ch


def set_file_logger(logger, log_filename, level=logging.DEBUG):
    # create file handler which logs even debug messages
    fh = logging.FileHandler(log_filename, mode="w")
    fh.setLevel(level)

    # create formatter and add it to the handlers
    # formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)

    # add the handlers to logger
    logger.addHandler(fh)
    # logger.info('test')
    return fh


def test_log1():
    logger = logging.getLogger(__name__)
    logger.info("x")
    set_logger_console(logger)
    logger.info("y")
    set_file_logger(logger, "a.txt")
    logger.info("a")
    set_file_logger(logger, "b.txt")
    logger.info("b")
    set_file_logger(logger, "c.txt")
    logger.info("c")


if __name__ == "__main__":
    test_log1()
