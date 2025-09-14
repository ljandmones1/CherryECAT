/*
 * Copyright (c) 2025, sakumisu
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef EC_MAILBOX_H
#define EC_MAILBOX_H

uint8_t *ec_mailbox_fill_send(ec_slave_t *slave, ec_datagram_t *datagram, uint8_t type, uint16_t size);
int ec_mailbox_send(ec_slave_t *slave, ec_datagram_t *datagram);
int ec_mailbox_receive(ec_slave_t *slave, ec_datagram_t *datagram, uint8_t *type, uint32_t *size);

#endif