# Copyright (C) 2013 Nippon Telegraph and Telephone Corporation.
# Copyright (C) 2015 Brad Cowie, Christopher Lorier and Joe Stringer.
# Copyright (C) 2015 Research and Education Advanced Network New Zealand Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os, signal, logging

from logging.handlers import TimedRotatingFileHandler

from valve import valve_factory
from util import kill_on_exception
from dp import DP

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller import dpset
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.controller import event
from ryu.ofproto import ofproto_v1_3, ether
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import vlan
from ryu.lib import hub

from nsodbc import nsodbc_factory


class EventFaucetReconfigure(event.EventBase):
    pass


class EventFaucetResolveGateways(event.EventBase):
    pass


class EventFaucetHostExpire(event.EventBase):
    pass


class Faucet(app_manager.RyuApp):
    """A Ryu app that performs layer 2 switching with VLANs.

    The intelligence is largely provided by a Valve class. Faucet's role is
    mainly to perform set up and to provide a communication layer between ryu
    and valve.
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    _CONTEXTS = {'dpset': dpset.DPSet}

    logname = 'faucet'
    exc_logname = logname + '.exception'

    def __init__(self, *args, **kwargs):
        super(Faucet, self).__init__(*args, **kwargs)

        # There doesnt seem to be a sensible method of getting command line
        # options into ryu apps. Instead I am using the environment variable
        # FAUCET_CONFIG to allow this to be set, if it is not set it will
        # default to valve.yaml
        self.config_file = os.getenv(
            'FAUCET_CONFIG', '/etc/ryu/faucet/faucet.yaml')
        self.logfile = os.getenv(
            'FAUCET_LOG', '/var/log/ryu/faucet/faucet.log')
        self.exc_logfile = os.getenv(
            'FAUCET_EXCEPTION_LOG', '/var/log/ryu/faucet/faucet_exception.log')

        # Set the signal handler for reloading config file
        signal.signal(signal.SIGHUP, self.signal_handler)

        # Create dpset object for querying Ryu's DPSet application
        self.dpset = kwargs['dpset']

        # Setup logging
        self.logger = logging.getLogger(self.logname)
        logger_handler = TimedRotatingFileHandler(
            self.logfile,
            when='midnight')
        log_fmt = '%(asctime)s %(name)-6s %(levelname)-8s %(message)s'
        logger_handler.setFormatter(
            logging.Formatter(log_fmt, '%b %d %H:%M:%S'))
        self.logger.addHandler(logger_handler)
        self.logger.propagate = 0
        self.logger.setLevel(logging.DEBUG)

        # Set up separate logging for exceptions
        exc_logger = logging.getLogger(self.exc_logname)
        exc_logger_handler = logging.FileHandler(self.exc_logfile)
        exc_logger_handler.setFormatter(
            logging.Formatter(log_fmt, '%b %d %H:%M:%S'))
        exc_logger.addHandler(exc_logger_handler)
        exc_logger.propagate = 1
        exc_logger.setLevel(logging.CRITICAL)

        dp = self.parse_config(self.config_file, self.logname)
        self.valve = valve_factory(dp)
        if self.valve is None:
            self.logger.error("Hardware type not supported")
	
        self.nsodbc = nsodbc_factory()
        self.conn = self.nsodbc.connect('driver=couchdb;server=localhost;' + \
                        'uid=root;pwd=admin')
        try:
            self.switch_database = self.conn.create('switches_bak')
        except Exception, e:
            self.switch_database = self.conn['switches_bak']
            if not self.switch_database:
                raise 
        
        self.conn1 = self.nsodbc.connect('driver=couchdb;server=localhost;' + \
                        'uid=root;pwd=admin')
        try:
            self.flow_database = self.conn1.create('flows_bak')
        except Exception, e:
            self.flow_database = self.conn1['flows_bak']
            if not self.flow_database:
                raise 

        self.gateway_resolve_request_thread = hub.spawn(
            self.gateway_resolve_request)
        self.host_expire_request_thread = hub.spawn(
            self.host_expire_request)

    def gateway_resolve_request(self):
        while True:
            self.send_event('Faucet', EventFaucetResolveGateways())
            hub.sleep(2)

    def host_expire_request(self):
        while True:
            self.send_event('Faucet', EventFaucetHostExpire())
            hub.sleep(5)

    def parse_config(self, config_file, log_name):
        new_dp = DP.parser(config_file, log_name)
        if new_dp:
            try:
                new_dp.sanity_check()
                return new_dp
            except AssertionError:
                self.logger.exception("Error in config file:")
        return None

    def send_flow_msgs(self, dp, flow_msgs):        
        self.valve.ofchannel_log(flow_msgs)
        switch = None
        try:
            rows = self.switch_database.get_docs('_design/switches/_view/switch', key=str(hex(dp.id)))
            switch = rows[0]
        except:
            # switch event not triggered yet
            switch = None
        for flow_msg in flow_msgs:
            flow_msg.datapath = dp
            dp.send_msg(flow_msg)
            flow_object = {'data':flow_msg.to_jsondict(), 'tags': []}
            flow_id = self.flow_database.insert_update_doc(flow_object, '')
            if switch:
                switch.value['data']['flows'].append(flow_id)
                self.switch_database.insert_update_doc(switch.value, 'data')

    def signal_handler(self, sigid, frame):
        if sigid == signal.SIGHUP:
            self.send_event('Faucet', EventFaucetReconfigure())

    @set_ev_cls(EventFaucetReconfigure, MAIN_DISPATCHER)
    def reload_config(self, ev):
        new_config_file = os.getenv('FAUCET_CONFIG', self.config_file)
        new_dp = self.parse_config(new_config_file, self.logname)
        if new_dp:
            flowmods = self.valve.reload_config(new_dp)
            ryudp = self.dpset.get(new_dp.dp_id)
            self.send_flow_msgs(ryudp, flowmods)

    @set_ev_cls(EventFaucetResolveGateways, MAIN_DISPATCHER)
    def resolve_gateways(self, ev):
        if self.valve is not None:
            flowmods = self.valve.resolve_gateways()
            if flowmods:
                ryudp = self.dpset.get(self.valve.dp.dp_id)
                self.send_flow_msgs(ryudp, flowmods)

    @set_ev_cls(EventFaucetHostExpire, MAIN_DISPATCHER)
    def host_expire(self, ev):
        if self.valve is not None:
            self.valve.host_expire()

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    @kill_on_exception(exc_logname)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        self.valve.ofchannel_log([msg])

        pkt = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocols(ethernet.ethernet)[0]
        eth_type = eth_pkt.ethertype

        if eth_type == ether.ETH_TYPE_8021Q:
            # tagged packet
            vlan_proto = pkt.get_protocols(vlan.vlan)[0]
            vlan_vid = vlan_proto.vid
        else:
            return

        in_port = msg.match['in_port']
        flowmods = self.valve.rcv_packet(dp.id, in_port, vlan_vid, pkt)
        self.send_flow_msgs(dp, flowmods)

    @set_ev_cls(ofp_event.EventOFPErrorMsg, MAIN_DISPATCHER)
    @kill_on_exception(exc_logname)
    def _error_handler(self, ev):
        msg = ev.msg
        self.valve.ofchannel_log([msg])
        self.logger.error('Got OFError: %s', msg)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def handler_features(self, ev):
        msg = ev.msg
        dp = msg.datapath
        flowmods = self.valve.switch_features(dp.id, msg)
        self.send_flow_msgs(dp, flowmods)

    @set_ev_cls(dpset.EventDP, dpset.DPSET_EV_DISPATCHER)
    @kill_on_exception(exc_logname)
    def handler_connect_or_disconnect(self, ev):
        dp = ev.dp

        switch_object = {'_id': str(hex(dp.id)), 'data':{'flows':[]}}
        self.switch_database.insert_update_doc(switch_object, 'data')

        if not ev.enter:
            # Datapath down message
            self.logger.debug('DP %s disconnected' % str(dp.id))
            self.valve.datapath_disconnect(dp.id)

            rows = self.switch_database.get_docs('_design/switches/_view/switch', key=str(hex(dp.id)))
            switch = rows[0].value
            for flow_id in switch['data']['flows']:
                 self.flow_database.delete_doc(str(flow_id))

            # Delete switch from database
            self.switch_database.delete_doc(str(hex(dp.id)))
            return

        self.logger.debug('DP %s connected' % str(dp.id))
        self.handler_datapath(dp)

    @set_ev_cls(dpset.EventDPReconnected, dpset.DPSET_EV_DISPATCHER)
    @kill_on_exception(exc_logname)
    def handler_reconnect(self, ev):
        dp = ev.dp
        self.logger.debug('DP %s reconnected' % str(dp.id))
        self.handler_datapath(dp)

    def handler_datapath(self, dp):
        discovered_ports = [
            p.port_no for p in dp.ports.values() if p.state == 0]
        flowmods = self.valve.datapath_connect(dp.id, discovered_ports)
        self.send_flow_msgs(dp, flowmods)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    @kill_on_exception(exc_logname)
    def port_status_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = msg.datapath.ofproto
        reason = msg.reason
        port_no = msg.desc.port_no

        flowmods = []
        if reason == ofp.OFPPR_ADD:
            flowmods = self.valve.port_add(dp.id, port_no)
        elif reason == ofp.OFPPR_DELETE:
            flowmods = self.valve.port_delete(dp.id, port_no)
        elif reason == ofp.OFPPR_MODIFY:
            port_down = msg.desc.state & ofp.OFPPS_LINK_DOWN
            if port_down:
                flowmods = self.valve.port_delete(dp.id, port_no)
            else:
                flowmods = self.valve.port_add(dp.id, port_no)
        else:
            self.logger.warning('Unhandled port status %s for port %u',
                                reason, port_no)

        self.send_flow_msgs(dp, flowmods)
