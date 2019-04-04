from copy import copy
import datetime
from sysdata.mongodb.mongo_connection import mongoConnection, MONGO_ID_KEY

class logger(object):
    """
    log: used for writing messages

    Messages are datestamped, and tagged with attributes for storage / processing

    This is the base class

    Will also do reporting and emailing of errors


    """

    def __init__(self, thing="", log_level="Off", **kwargs):
        """
        Base class for logging.

        >>> log=logger("base_system") ## set up a logger with type "base_system"
        >>> log
        Logger (off) attributes- type: base_system
        >>>
        >>> log=logger("another_system", stage="test") ## optionally add other attributes
        >>> log
        Logger (off) attributes- stage: test, type: another_system
        >>>
        >>> log2=logger(log, log_level="on", stage="combForecast") ## creates a copy of log
        >>> log
        Logger (off) attributes- stage: test, type: another_system
        >>> log2
        Logger (on) attributes- stage: combForecast, type: another_system
        >>>
        >>> log3=log2.setup(stage="test2") ## to avoid retyping; will make a copy so attributes aren't kept
        >>> log2
        Logger (on) attributes- stage: combForecast, type: another_system
        >>> log3
        Logger (on) attributes- stage: test2, type: another_system
        >>>
        >>> log3.label(instrument_code="EDOLLAR") ## adds the attribute without making a copy
        >>> log3
        Logger (on) attributes- instrument_code: EDOLLAR, stage: test2, type: another_system
        >>>
        >>>
        """

        if isinstance(thing, str):
            # been passed a label, so not inheriting anything
            log_attributes = dict(type=thing)
            other_attributes = kwargs

            log_attributes = get_update_attributes_list(
                log_attributes, other_attributes)

        elif hasattr(thing, "attributes"):
            # probably a log
            new_attributes = kwargs
            parent_attributes = thing.attributes

            log_attributes = get_update_attributes_list(
                parent_attributes, new_attributes)

        else:
            raise Exception(
                "Can only create a logger from another logger, or a str identifier"
            )

        setattr(self, "attributes", log_attributes)
        self.set_logging_level(log_level)

    def logging_level(self):
        return getattr(self, "_log_level", "Off")

    def set_logging_level(self, new_level):
        new_level = new_level.lower()
        allowed_levels = ["off", "terse", "on"]

        if new_level not in allowed_levels:
            raise Exception("You can't log with level %s", new_level)

        setattr(self, "_log_level", new_level)

    def __repr__(self):
        attributes = self.attributes
        attr_keys = sorted(attributes.keys())

        attribute_desc = [
            keyname + ": " + str(attributes[keyname]) for keyname in attr_keys
        ]
        return "Logger (%s) attributes- %s" % (self._log_level,
                                               ", ".join(attribute_desc))

    def setup(self, **kwargs):

        new_log = copy(self)

        log_attributes = new_log.attributes
        passed_attributes = kwargs

        new_attributes = get_update_attributes_list(log_attributes,
                                                    passed_attributes)

        setattr(new_log, "attributes", new_attributes)
        setattr(new_log, "_log_level", self.logging_level())

        return new_log

    def label(self, **kwargs):
        log_attributes = self.attributes
        passed_attributes = kwargs

        new_attributes = get_update_attributes_list(log_attributes,
                                                    passed_attributes)

        setattr(self, "attributes", new_attributes)

    def msg(self, text, **kwargs):
        self.log(text, msglevel=0, **kwargs)

    def terse(self, text, **kwargs):
        self.log(text, msglevel=1, **kwargs)

    def warn(self, text, **kwargs):
        self.log(text, msglevel=2, **kwargs)

    def error(self, text, **kwargs):
        self.log(text, msglevel=3, **kwargs)

    def critical(self, text, **kwargs):
        self.log(text, msglevel=4, **kwargs)

    def log(self, text, msglevel=0, **kwargs):
        log_attributes = self.attributes
        passed_attributes = kwargs

        use_attributes = get_update_attributes_list(log_attributes,
                                                    passed_attributes)

        self.log_handle_caller(msglevel, text, use_attributes)

    def log_handle_caller(self, msglevel, text, use_attributes):
        raise Exception(
            "You're using a base class for logger - you need to use an inherited class like logtoscreen()"
        )


def get_update_attributes_list(parent_attributes, new_attributes):
    """
    Merge these two dicts together
    """

    joined_attributes = copy(parent_attributes)
    for keyname in new_attributes.keys():
        joined_attributes[keyname] = new_attributes[keyname]

    return joined_attributes


class logtoscreen(logger):
    """
    Currently reports to stdout

    In future versions will print to log files and databases

    Will also do proper error handling

    """

    def log_handle_caller(self, msglevel, text, use_attributes):
        """
        >>> log=logtoscreen("base_system", log_level="off") ## this won't do anything
        >>> log.log("this wont print")
        >>> log.terse("nor this")
        >>> log.warn("this will")
        this will
        >>> log.error("and this")
        and this
        >>> log=logtoscreen(log, log_level="terse")
        >>> log.msg("this wont print")
        >>> log.terse("this will")
        this will
        >>> log=logtoscreen(log_level="on")
        >>> log.msg("now prints every little thing")
        now prints every little thing
        """
        log_level = self.logging_level()

        if msglevel == 0:
            if log_level == "on":
                print(text)
                # otherwise do nothing - either terse or off

        elif msglevel == 1:
            if log_level in ["on", "terse"]:
                print(text)
                # otherwise do nothing - either terse or off
        else:
            print(text)

        if msglevel == 3:
            print(text)

        if msglevel == 4:
            raise Exception(text)

MSG_LEVEL_DICT = dict(m0="", m1="", m2="[Warning]", m3="[Error]", m4="*CRITICAL*")

LEVEL_ID = "_Level" #use underscores so less chance of a conflict with labels used by users
TIMESTAMP_ID = "_Timestamp"
TEXT_ID = "_Text"
LOG_COLLECTION_NAME = "Logs"

class logToMongod(logger):
    """
    Logs to a mongodb

    """
    def __init__(self, mongo_db = None, thing="", log_level="Off", **kwargs):
        self._mongo = mongoConnection(LOG_COLLECTION_NAME, mongo_db=mongo_db)

        super().__init__(thing = thing, log_level = log_level, ** kwargs)

        # this won't create the index if it already exists
        self._mongo.create_multikey_index(TIMESTAMP_ID, LEVEL_ID)

    def log_handle_caller(self, msglevel, text, use_attributes):
        """
        Ignores log_level - logs everything, just in case

        Doesn't raise exceptions

        """
        log_dict = copy(use_attributes)

        msg_level_text = MSG_LEVEL_DICT["m%d" % msglevel]

        datetime_now = datetime.datetime.now()

        log_dict[LEVEL_ID] = msg_level_text
        log_dict[TIMESTAMP_ID] = datetime_now
        log_dict[TEXT_ID] = text

        self._mongo.collection.insert_one(log_dict)

        print("%s %s %s %s" % (datetime_now, str(use_attributes), text))

class accessLogFromMongodb(object):

    def __init__(self, mongo_db=None):
        self._mongo = mongoConnection(LOG_COLLECTION_NAME, mongo_db=mongo_db)

    def get_log_items(self, attribute_dict=dict(), lookback_days=1):
        """
        Return log items as list of text

        :param attribute_dict: dictionary of attributes to return logs for
        :return: list of str
        """

        results = self.get_log_items_as_tuple(attribute_dict, lookback_days=lookback_days)

        # jam together as text
        results_as_text = ["%s %s %s %s" %
            (str(ts_single), str(attribute_single), str(level_single), str(text_single)) for
                   ts_single, level_single, text_single, attribute_single in
                   results]

        return results_as_text

    def get_log_items_as_tuple(self, attribute_dict=dict(), lookback_days=1):
        """
        Return log items not as text, good for diagnostics

        :param attribute_dict: dictionary of attributes to return logs for
        :return: list of 4-typles: timestamp, level, text, attributes
        """

        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=lookback_days)
        timestamp_dict = {}
        timestamp_dict["$lt"] = cutoff_date
        attribute_dict[TIMESTAMP_ID] = timestamp_dict

        result_dict = self._mongo.collection.find(attribute_dict)
        result_dict = [single_log_dict for single_log_dict in result_dict]
        _removed_ids_not_used = [single_log_dict.pop(MONGO_ID_KEY) for single_log_dict in result_dict]

        # convert to tuples: timestamp, attributes, text, level
        timestamps, levels, text_list, attribute_dict = self._from_list_of_results_to_list_of_tuples(result_dict)

        # convert to list of tuples, one per record
        results = [(ts_single, level_single, text_single, attribute_single) for
                   ts_single, level_single, text_single, attribute_single in
                   zip(timestamps, levels, text_list, attribute_dict)]

        # sort by timestamp
        results = sorted(results, key=lambda tup:tup[0])

        return results



    def _from_list_of_results_to_list_of_tuples(self, result_dict):
        # convert to list of tuples: timestamp, attributes, text, level

        timestamps = [single_log_dict.pop(TIMESTAMP_ID) for single_log_dict in result_dict]
        levels = [single_log_dict.pop(LEVEL_ID) for single_log_dict in result_dict]
        text_list = [single_log_dict.pop(TEXT_ID) for single_log_dict in result_dict]
        attribute_dict = result_dict

        return timestamps, levels, text_list, attribute_dict


    def delete_log_items_from_before_n_days(self, days=365):

        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        attribute_dict={}
        timestamp_dict = {}
        timestamp_dict["$lt"] = cutoff_date
        attribute_dict[TIMESTAMP_ID] = timestamp_dict

        self._mongo.collection.remove(attribute_dict)

        # need something to delete old log records, eg more than x months ago

if __name__ == '__main__':
    import doctest
    doctest.testmod()
