import gamelib
import random
import math
import warnings
from sys import maxsize
import json

from collections import Counter

TL = 0
TR = 1
BL = 2
BR = 3
EL = 4
ER = 5


"""
Most of the algo code you write will be in this file unless you create new
modules yourself. Start by modifying the 'on_turn' function.

Advanced strategy tips: 

  - You can analyze action frames by modifying on_action_frame function

  - The GameState.map object can be manually manipulated to create hypothetical 
  board states. Though, we recommended making a copy of the map to preserve 
  the actual current map state.
"""

class AlgoStrategy(gamelib.AlgoCore):
    def __init__(self):
        super().__init__()
        seed = random.randrange(maxsize)
        random.seed(seed)
        gamelib.debug_write('Random seed: {}'.format(seed))
        self.last_corner = TL

    def on_game_start(self, config):
        """ 
        Read in config and perform any initial setup here 
        """
        gamelib.debug_write('Configuring your custom algo strategy...')
        self.config = config
        global FILTER, ENCRYPTOR, DESTRUCTOR, PING, EMP, SCRAMBLER
        FILTER = config["unitInformation"][0]["shorthand"]
        ENCRYPTOR = config["unitInformation"][1]["shorthand"]
        DESTRUCTOR = config["unitInformation"][2]["shorthand"]
        PING = config["unitInformation"][3]["shorthand"]
        EMP = config["unitInformation"][4]["shorthand"]
        SCRAMBLER = config["unitInformation"][5]["shorthand"]
        # This is a good place to do initial setup
        self.scored_on_locations = []
        self.recent_breaches = []

        self.info = {
            'd': DESTRUCTOR,
            'f': FILTER,
            'e': ENCRYPTOR
        }


    def on_turn(self, turn_state):
        """
        This function is called every turn with the game state wrapper as
        an argument. The wrapper stores the state of the arena and has methods
        for querying its state, allocating your current resources as planned
        unit deployments, and transmitting your intended deployments to the
        game engine.
        """
        game_state = gamelib.GameState(self.config, turn_state)
        #gamelib.debug_write('Performing turn {} of your custom algo strategy'.format(game_state.turn_number))
        game_state.suppress_warnings(True)  #Comment or remove this line to enable warnings.

        self.starter_strategy(game_state)

        self.recent_breaches = []
        game_state.submit_turn()


    """
    NOTE: All the methods after this point are part of the sample starter-algo
    strategy and can safely be replaced for your custom algo.
    """

    TOPLEFT = [
        ('f', [[3, 13]]),
        ('d', [[1, 12], [2, 12], [3, 12], [3, 11]]),
        ('f', [[0, 13], [1, 13], [2, 13], [4, 12]]),
        ('d', [[4, 11], [4, 10]]),
        ('f', [[5, 11], [7, 11]]),
        ('d', [[5, 10]]),
        ('f', [[6, 11]]),
        ('d', [[6, 10], [6, 9], [5, 9]]),
        ('f', [[7, 11]]),
        ('d', [[7, 10], [7, 9]]),
        ('f', [[8, 11]]),
        ('d', [[8, 10], [8, 9]]),
    ]

    BOTLEFT = [
        ('d', [[9, 6], [10, 6], [11, 6]]),
        ('f', [[10, 7]]),
        ('f', [[9, 8]]),
        ('d', [[8, 7], [9, 7], [8, 6]]),
        ('d', [[10, 5], [11, 5], [12, 5]]),
        ('f', [[11, 9]]),
        ('d', [[11, 8], [11, 7]]),
        ('f', [[12, 9]]),
        ('d', [[12, 8], [12, 7], [12, 6]]),
        ('d', [[7, 8], [8, 8], [7, 7]]),
    ]

    ENLEFT = [
        ('e', [[9, 5], [10, 5], [11, 5], [12, 5], [11, 4], [12, 4], [8, 5], [9, 4],
            [10, 4], [11, 2], [12, 2], [13, 2], [12, 1], [13, 1], [13, 0]]),
    ]

    def spawnCore(self, game_state, side, coreLimit=None):
        if side in (TL, TR):
            plan = self.TOPLEFT
        elif side in (BL, BR):
            plan = self.BOTLEFT
        else:
            plan = self.ENLEFT

        initcores = game_state.get_resource(game_state.CORES)

        for group in plan:
            typ = self.info[group[0]]
            for loc in group[1]:
                nowcores = game_state.get_resource(game_state.CORES)
                if coreLimit is not None and initcores - nowcores >= coreLimit:
                    return
                if nowcores < 1:
                    return

                if side in (TR, BR, ER):
                    x = 27 - loc[0]
                else:
                    x = loc[0]

                y = loc[1]

                game_state.attempt_spawn(typ, [x, y])

    def starter_strategy(self, game_state):
        """
        For defense we will use a spread out layout and some Scramblers early on.
        We will place destructors near locations the opponent managed to score on.
        For offense we will use long range EMPs if they place stationary units near the enemy's front.
        If there are no stationary units to attack in the front, we will send Pings to try and score quickly.
        """

        for plan in (self.TOPLEFT, self.BOTLEFT):
            for group in plan[:2]:
                typ = self.info[group[0]]
                for loc in group[1]:
                    game_state.attempt_spawn(typ, [loc[0], loc[1]])
                    game_state.attempt_spawn(typ, [27 - loc[0], loc[1]])

        bits = game_state.get_resource(game_state.BITS)

        # To simplify we will just check sending them from back left and right
        ping_spawn_location_options = [[10, 3], [17, 3]]
        best_location = self.least_damage_spawn_location(game_state, ping_spawn_location_options)

        if best_location == ping_spawn_location_options[0]:
            self.handle_attack(game_state, 0)
        else:
            self.handle_attack(game_state, 1)

        game_state.attempt_spawn(PING, best_location, 1000)

        cores = game_state.get_resource(game_state.CORES)

        corner = self.hardest_hit(game_state)

        #if cores >= 10:
        #    first_priority_cores = (2/3) * cores
        #    self.spawnCore(game_state, hits[0], first_priority_cores)
        #    self.spawnCore(game_state, hits[1], cores - first_priority_cores)
        #else:
        self.spawnCore(game_state, corner)

        cores = game_state.get_resource(game_state.CORES)

        if cores >= 1:
            self.spawnCore(game_state, corner)

    def handle_encryption_tunnel(self, game_state):
        # LEFT_BUILD_ORDER = [(9,5), (10,5), (11,5), (12,5), (10,3), (11,3), (12,3), (13,3)]
        # RIGHT_BUILD_ORDER = [(15,5), (16,5), (17,5), (18,5), (17,3), (16, 3), (15, 3), (14, 3)]

        # NET_BUILD_ORDER = LEFT_BUILD_ORDER[:4] + RIGHT_BUILD_ORDER[:4] + LEFT_BUILD_ORDER[4:] + RIGHT_BUILD_ORDER[4:]

        NET_BUILD_ORDER = [(12,1), (15,1), (13,1), (14,3), (13,3), (14,4), (10,3), (10,4), (17,3), (17,4), (13,4), (12,3), (15,3), (12,4), (15,4)]

        # this should build or rebuild in the correct order
        net_spawn_list = []
        my_remaining_cores = game_state.get_resource(game_state.CORES) # keeps track until you can't build more
        for location in NET_BUILD_ORDER:
            if my_remaining_cores == 0:
                break
            elif game_state.can_spawn(ENCRYPTOR, location):
                net_spawn_list.append(location)
                my_remaining_cores -= 1

        if len(net_spawn_list) > 0:
            game_state.attempt_spawn(ENCRYPTOR, net_spawn_list)

    def handle_attack(self, game_state, index):
        RUSH_BIT_SIZE = 10
        # SPAWN_LOCATIONS = [[9,4], [18,4]] # left or right
        SPAWN_LOCATIONS = [[13,0], [14,0]]

        numBits = int(game_state.get_resource(game_state.BITS))
        if numBits >= RUSH_BIT_SIZE:
            self.handle_encryption_tunnel(game_state)
            game_state.attempt_spawn(PING, [SPAWN_LOCATIONS[index]] * RUSH_BIT_SIZE)


    def hardest_hit(self, game_state):
        hits = Counter()
        for loc in self.recent_breaches:
            if loc[0] <= 13:
                if loc[1] >= 7:
                    hits[TL] += 1
                else:
                    hits[BL] += 1
            else:
                if loc[1] >= 7:
                    hits[TR] += 1
                else:
                    hits[BR] += 1

        #return max((h, i) for (i, h) in enumerate(hits))[1]
        mc = hits.most_common(1)
        if not mc:
            return self.last_corner

        c = mc[0][0]
        self.last_corner = c

        gamelib.debug_write("det loc: {}".format(c))
        return c

    def least_damage_spawn_location(self, game_state, location_options):
        """
        This function will help us guess which location is the safest to spawn moving units from.
        It gets the path the unit will take then checks locations on that path to
        estimate the path's damage risk.
        """

        damages = []
        # Get the damage estimate each path will take
        for location in location_options:
            path = game_state.find_path_to_edge(location)
            damage = 0
            if path is None:
                damage = 10000
            else:
                for path_location in path:
                    # Get number of enemy destructors that can attack the final location and multiply by destructor damage
                    damage += len(game_state.get_attackers(path_location, 0)) * gamelib.GameUnit(DESTRUCTOR, game_state.config).damage
            damages.append(damage)

        # Now just return the location that takes the least damage
        return location_options[damages.index(min(damages))]

    def on_action_frame(self, turn_string):
        """
        This is the action frame of the game. This function could be called
        hundreds of times per turn and could slow the algo down so avoid putting slow code here.
        Processing the action frames is complicated so we only suggest it if you have time and experience.
        Full doc on format of a game frame at: https://docs.c1games.com/json-docs.html
        """
        # Let's record at what position we get scored on
        state = json.loads(turn_string)
        events = state["events"]
        breaches = events["breach"]
        for breach in breaches:
            location = breach[0]
            unit_owner_self = True if breach[4] == 1 else False
            # When parsing the frame data directly, 
            # 1 is integer for yourself, 2 is opponent (StarterKit code uses 0, 1 as player_index instead)
            if not unit_owner_self:
                gamelib.debug_write("Got scored on at: {}".format(location))
                self.scored_on_locations.append(location)
                self.recent_breaches.append(location)
                gamelib.debug_write("All locations: {}".format(self.scored_on_locations))
                gamelib.debug_write("recent locations: {}".format(self.recent_breaches))


if __name__ == "__main__":
    algo = AlgoStrategy()
    algo.start()
