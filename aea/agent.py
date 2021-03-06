# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2018-2019 Fetch.AI Limited
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""This module contains the implementation of a generic agent."""

import logging
import time
from abc import ABC, abstractmethod
from asyncio import AbstractEventLoop
from enum import Enum
from typing import List, Optional

from aea.connections.base import Connection
from aea.identity.base import Identity
from aea.mail.base import InBox, Multiplexer, OutBox

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Enumeration for an agent state.

    In particular, it can be one of the following states:

    - AgentState.INITIATED: when the Agent object has been created.
    - AgentState.CONNECTED: when the agent is connected.
    - AgentState.RUNNING: when the agent is running.
    """

    INITIATED = "initiated"
    CONNECTED = "connected"
    RUNNING = "running"


class Liveness:
    """Determines the liveness of the agent."""

    def __init__(self):
        """Instantiate the liveness."""
        self._is_stopped = True

    @property
    def is_stopped(self) -> bool:
        """Check whether the liveness is stopped."""
        return self._is_stopped

    def start(self) -> None:
        """Start the liveness."""
        self._is_stopped = False

    def stop(self) -> None:
        """Stop the liveness."""
        self._is_stopped = True


class Agent(ABC):
    """This class provides an abstract base class for a generic agent."""

    def __init__(
        self,
        identity: Identity,
        connections: List[Connection],
        loop: Optional[AbstractEventLoop] = None,
        timeout: float = 1.0,
        is_debug: bool = False,
        is_programmatic: bool = True,  # TODO to remove
    ) -> None:
        """
        Instantiate the agent.

        :param identity: the identity of the agent.
        :param connections: the list of connections of the agent.
        :param loop: the event loop to run the connections.
        :param timeout: the time in (fractions of) seconds to time out an agent between act and react
        :param is_debug: if True, run the agent in debug mode (does not connect the multiplexer).
        :param is_programmatic: if True, run the agent in programmatic mode (skips loading of resources from directory).

        :return: None
        """
        self._identity = identity
        self._connections = connections

        self._multiplexer = Multiplexer(self._connections, loop=loop)
        self._inbox = InBox(self._multiplexer)
        self._outbox = OutBox(self._multiplexer)
        self._liveness = Liveness()
        self._timeout = timeout

        self._tick = 0

        self.is_debug = is_debug

    @property
    def identity(self) -> Identity:
        """Get the identity."""
        return self._identity

    @property
    def multiplexer(self) -> Multiplexer:
        """Get the multiplexer."""
        return self._multiplexer

    @property
    def inbox(self) -> InBox:
        """
        Get the inbox.

        The inbox contains Envelopes from the Multiplexer.
        The agent can pick these messages for processing.
        """
        return self._inbox

    @property
    def outbox(self) -> OutBox:
        """
        Get the outbox.

        The outbox contains Envelopes for the Multiplexer.
        Envelopes placed in the Outbox are processed by the Multiplexer.
        """
        return self._outbox

    @property
    def name(self) -> str:
        """Get the agent name."""
        return self.identity.name

    @property
    def liveness(self) -> Liveness:
        """Get the liveness."""
        return self._liveness

    @property
    def tick(self) -> int:
        """
        Get the tick (or agent loop count).

        Each agent loop (one call to each one of act(), react(), update()) increments the tick.
        """
        return self._tick

    @property
    def agent_state(self) -> AgentState:
        """
        Get the state of the agent.

        :raises ValueError: if the state does not satisfy any of the foreseen conditions.
        :return: None
        """
        if (
            self.multiplexer is not None
            and not self.multiplexer.connection_status.is_connected
        ):
            return AgentState.INITIATED
        elif (
            self.multiplexer.connection_status.is_connected and self.liveness.is_stopped
        ):
            return AgentState.CONNECTED
        elif (
            self.multiplexer.connection_status.is_connected
            and not self.liveness.is_stopped
        ):
            return AgentState.RUNNING
        else:
            raise ValueError("Agent state not recognized.")  # pragma: no cover

    def start(self) -> None:
        """
        Start the agent.

        Performs the following:

        - calls connect() on the multiplexer (unless in debug mode), and
        - calls setup(), and
        - calls start() on the liveness, and
        - enters the agent main loop.

        While the liveness of the agent is not stopped it continues to loop over:

        - increment the tick,
        - call to act(),
        - sleep for specified timeout,
        - call to react(),
        - call to update().

        :return: None
        """
        if not self.is_debug:
            self.multiplexer.connect()

        logger.debug("[{}]: Calling setup method...".format(self.name))
        self.setup()

        self.liveness.start()
        self._run_main_loop()

    def _run_main_loop(self) -> None:
        """
        Run the main loop of the agent.

        :return: None
        """
        logger.debug("[{}]: Start processing messages...".format(self.name))
        while not self.liveness.is_stopped:
            self._tick += 1
            self.act()
            time.sleep(self._timeout)
            self.react()
            self.update()
        logger.debug("[{}]: Exiting main loop...".format(self.name))

    def stop(self) -> None:
        """
        Stop the agent.

        Performs the following:

        - calls stop() on the liveness, and
        - calls teardown(), and
        - calls disconnect() on the multiplexer.

        :return: None
        """
        self.liveness.stop()
        logger.debug("[{}]: Calling teardown method...".format(self.name))
        self.teardown()

        logger.debug("[{}]: Stopping message processing...".format(self.name))
        self.multiplexer.disconnect()

    @abstractmethod
    def setup(self) -> None:
        """
        Set up the agent.

        :return: None
        """

    @abstractmethod
    def act(self) -> None:
        """
        Perform actions.

        :return: None
        """

    @abstractmethod
    def react(self) -> None:
        """
        React to events.

        :return: None
        """

    @abstractmethod
    def update(self) -> None:
        """
        Update the internal state of the agent.

        :return None
        """

    @abstractmethod
    def teardown(self) -> None:
        """
        Tear down the agent.

        :return: None
        """
