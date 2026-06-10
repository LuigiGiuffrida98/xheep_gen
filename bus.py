from bus_type import BusType
from copy import deepcopy
from typing import List, Optional

from peripherals.abstractions import Peripheral, PeripheralDomain


class Bus:
    """
    Represents a system bus.

    In bus-centric systems (see :class:`XAlp`) the bus is created first and
    every component (CPU, memory subsystem, peripheral subsystems) is then
    connected to it.

    :param BusType bus_type: The type of the bus.
    :raise TypeError: when parameters are of incorrect type.
    """

    def __init__(
        self,
        bus_type: BusType,
        peripherals: Optional[List[Peripheral]] = None,
        domains: Optional[List[PeripheralDomain]] = None,
    ):
        if not type(bus_type) is BusType:
            raise TypeError(
                f"Bus.bus_type should be of type BusType not {type(bus_type)}"
            )
        self._bus_type = bus_type
        self._peripherals = []
        self._domains = []

        if domains is not None:
            if peripherals is not None:
                raise ValueError(
                    "Bus should be configured with either peripherals or domains, not both"
                )
            self.set_domains(domains)
        elif peripherals is not None:
            self._set_peripherals_or_domains(peripherals)

    def bus_type(self) -> BusType:
        """
        :return: the type of the bus
        :rtype: BusType
        """
        return self._bus_type

    # ------------------------------------------------------------
    # Peripherals / Domains
    # ------------------------------------------------------------

    def _set_peripherals_or_domains(self, entries):
        if type(entries) is not list:
            raise TypeError("Bus peripherals or domains should be of type list")
        if all(isinstance(entry, PeripheralDomain) for entry in entries):
            self.set_domains(entries)
        elif all(isinstance(entry, Peripheral) for entry in entries):
            self.set_peripherals(entries)
        else:
            raise TypeError(
                "Bus entries should be either all Peripheral instances or all PeripheralDomain instances"
            )

    def set_peripherals(self, peripherals: List[Peripheral]):
        """
        Configure the bus with a flat list of peripherals. This represents a
        single bus address space.

        :param list[Peripheral] peripherals: Peripherals connected to the bus.
        """
        if type(peripherals) is not list:
            raise TypeError("Bus.peripherals should be of type list")
        if not all(isinstance(peripheral, Peripheral) for peripheral in peripherals):
            raise TypeError("Bus.peripherals should contain only Peripheral objects")
        self._peripherals = [deepcopy(peripheral) for peripheral in peripherals]
        self._domains = []

    def add_peripheral(self, peripheral: Peripheral):
        """
        Add a peripheral to a flat bus address space.
        """
        if not isinstance(peripheral, Peripheral):
            raise TypeError("Bus peripheral should be of type Peripheral")
        if self._domains:
            raise ValueError("Cannot add a flat peripheral to a bus configured with domains")
        self._peripherals.append(deepcopy(peripheral))

    def get_peripherals(self):
        """
        :return: A copy of the flat peripheral list.
        :rtype: list[Peripheral]
        """
        return [deepcopy(peripheral) for peripheral in self._peripherals]

    def set_domains(self, domains: List[PeripheralDomain]):
        """
        Configure the bus with a list of peripheral domains.

        :param list[PeripheralDomain] domains: Peripheral domains connected to the bus.
        """
        if type(domains) is not list:
            raise TypeError("Bus.domains should be of type list")
        if not all(isinstance(domain, PeripheralDomain) for domain in domains):
            raise TypeError("Bus.domains should contain only PeripheralDomain objects")
        self._domains = [deepcopy(domain) for domain in domains]
        self._peripherals = []

    def add_domain(self, domain: PeripheralDomain):
        """
        Add a peripheral domain to the bus.
        """
        if not isinstance(domain, PeripheralDomain):
            raise TypeError("Bus domain should be of type PeripheralDomain")
        if self._peripherals:
            raise ValueError("Cannot add a domain to a bus configured with peripherals")
        self._domains.append(deepcopy(domain))

    def get_domains(self):
        """
        :return: A copy of the peripheral domains connected to the bus.
        :rtype: list[PeripheralDomain]
        """
        return [deepcopy(domain) for domain in self._domains]

    def get_all_peripherals(self):
        """
        :return: A copy of all peripherals connected directly or through domains.
        :rtype: list[Peripheral]
        """
        if self._domains:
            peripherals = []
            for domain in self._domains:
                peripherals.extend(domain.get_peripherals())
            return peripherals
        return self.get_peripherals()

    # ------------------------------------------------------------
    # Address Map
    # ------------------------------------------------------------

    def generate_address_map(self, start_address: int = 0):
        """
        Automatically assign missing peripheral addresses and return the bus
        address map.

        Flat peripherals are placed sequentially in the bus address space.
        Domain-backed peripherals are placed by each domain and reported with
        absolute addresses (`domain.start_address + peripheral.offset`).

        :param int start_address: First address used for flat peripherals.
        :return: Address map entries.
        :rtype: list[dict]
        """
        if type(start_address) is not int or start_address < 0:
            raise ValueError("start_address should be a positive integer")

        if self._domains:
            for domain in self._domains:
                domain.build()
            return self.get_address_map()

        next_address = start_address
        for peripheral in self._peripherals:
            address = peripheral.get_address()
            if address is None:
                peripheral.set_address(next_address)
                address = next_address
            if address < next_address:
                raise ValueError(
                    f"Peripheral {peripheral.get_name()} starts at {hex(address)}, before the next free bus address {hex(next_address)}"
                )
            next_address = address + peripheral.get_size_bytes()

        self._validate_flat_address_map()
        return self.get_address_map()

    def get_address_map(self):
        """
        :return: The current address map.
        :rtype: list[dict]
        """
        if self._domains:
            address_map = []
            for domain in self._domains:
                for peripheral in domain.get_peripherals():
                    if peripheral.get_address() is None:
                        continue
                    address_map.append(
                        {
                            "domain": domain.get_name(),
                            "name": peripheral.get_name(),
                            "address": domain.get_start_address()
                            + peripheral.get_address(),
                            "offset": peripheral.get_address(),
                            "size": peripheral.get_size_bytes(),
                        }
                    )
            return sorted(address_map, key=lambda entry: entry["address"])

        return sorted(
            [
                {
                    "domain": None,
                    "name": peripheral.get_name(),
                    "address": peripheral.get_address(),
                    "offset": peripheral.get_address(),
                    "size": peripheral.get_size_bytes(),
                }
                for peripheral in self._peripherals
                if peripheral.get_address() is not None
            ],
            key=lambda entry: entry["address"],
        )

    def _validate_flat_address_map(self):
        peripherals = sorted(
            self._peripherals,
            key=lambda peripheral: peripheral.get_address(),
        )
        for current, next_peripheral in zip(peripherals, peripherals[1:]):
            current_end = current.get_address() + current.get_size_bytes()
            if current_end > next_peripheral.get_address():
                raise ValueError(
                    f"Peripheral {current.get_name()} overflows over {next_peripheral.get_name()}"
                )
